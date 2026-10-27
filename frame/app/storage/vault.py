# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 14:52
# @Modified  : 2026-10-24 23:40
# @Python    : 3.14.9
# @Description: Accnary app / storage / vault
"""KdbxVault: the storage-layer wrapper around one KDBX 4 file.

Responsibilities:
- create / unlock / lock, master-password rotation
- safe save with conflict detection and write-ahead verification
- format guards (refuse write-back of formats Accnary does not own)

The vault never interprets account structure - it is a secure container.
Catalog semantics live in app/services/catalog_service.py.

Safe-save flow (spec section 7):
1. refuse if the on-disk file changed since it was opened (conflict)
2. write a complete new encrypted file to a temp path next to the target
3. re-open the temp file and verify entry/group structure survived
4. copy the previous file to a .bak snapshot
5. atomically os.replace() temp over the target
6. on any failure: delete the temp file and raise, leaving the previous
   version (and its .bak) untouched
"""

from __future__ import annotations

import hashlib
from io import BytesIO
import os
from dataclasses import dataclass
from pathlib import Path

from pykeepass import PyKeePass, create_database
from pykeepass.exceptions import CredentialsError

from app.storage.atomic import copy_snapshot, same_contents, temporary_path, writer_lock

from app.errors import (
    BadCredentialsError,
    ConflictError,
    SafeSaveError,
    UnsupportedFormatError,
    VaultError,
    VaultFormatError,
    VaultLockedError,
    VaultNotFoundError,
)

#: The only KDBX version Accnary writes. Anything else opens read-only.
SUPPORTED_WRITE_VERSION = (4, 0)

_TMP_MARK = ".accnary-tmp-"
_BAK_SUFFIX = ".bak"


def file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except FileNotFoundError:
        return None


@dataclass(frozen=True)
class FormatInfo:
    version: tuple[int, int]
    cipher: str
    kdf: str

    @property
    def writable(self) -> bool:
        return self.version == SUPPORTED_WRITE_VERSION


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


class KdbxVault:
    """One opened, unlocked KDBX file. Not thread-safe; one per window."""

    def __init__(self, kp: PyKeePass, path: Path, opened_hash: str | None):
        self._kp = kp
        self.path = Path(path)
        self._opened_hash = opened_hash

    # -- construction -------------------------------------------------------

    @classmethod
    def create(cls, path: str | Path, password: str) -> "KdbxVault":
        target = Path(path)
        if target.exists():
            raise VaultError(f"refusing to overwrite an existing file: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with writer_lock(target):
            if target.exists():
                raise VaultError(f"refusing to overwrite an existing file: {target}")
            tmp = temporary_path(target)
            try:
                with tmp.open("wb") as handle:
                    kp = create_database(handle, password=password)
                    handle.flush()
                    os.fsync(handle.fileno())
                check = PyKeePass(str(tmp), password=password)
                if not same_contents(kp, check):
                    raise VaultFormatError("new vault failed content verification")
                # Windows rename refuses an existing destination (unlike replace).
                os.rename(tmp, target)
                kp.filename = str(target)
            except Exception as exc:
                raise VaultFormatError(f"could not create vault ({type(exc).__name__})") from exc
            finally:
                _unlink(tmp)
        return cls(kp, target, file_sha256(target))

    @classmethod
    def unlock(cls, path: str | Path, password: str) -> "KdbxVault":
        target = Path(path)
        if not target.is_file():
            raise VaultNotFoundError(f"vault file not found: {target}")
        try:
            encrypted = target.read_bytes()
            kp = PyKeePass(BytesIO(encrypted), password=password)
            kp.filename = str(target)
        except CredentialsError as exc:
            raise BadCredentialsError(f"wrong master password for {target}") from exc
        except Exception as exc:
            raise VaultFormatError(f"could not parse vault {target}: {exc}") from exc
        vault = cls(kp, target, hashlib.sha256(encrypted).hexdigest())
        try:
            with writer_lock(target):
                vault._cleanup_stale_tmp()
        except (ConflictError, OSError):
            pass  # an active save owns its temp files; opening remains read-only
        return vault

    # -- state --------------------------------------------------------------

    @property
    def is_locked(self) -> bool:
        return self._kp is None

    @property
    def kp(self) -> PyKeePass:
        """The underlying pykeepass handle (storage-internal use)."""
        if self._kp is None:
            raise VaultLockedError("vault is locked")
        return self._kp

    @property
    def format_info(self) -> FormatInfo:
        kp = self.kp
        return FormatInfo(
            version=tuple(kp.version),
            cipher=str(kp.encryption_algorithm),
            kdf=str(kp.kdf_algorithm),
        )

    def lock(self) -> None:
        """Drop the decrypted database and credentials (best-effort wipe:
        Python cannot guarantee every string copy is erased - documented risk)."""
        self._kp = None

    # -- saving --------------------------------------------------------------

    def save(self, *, validator=None) -> None:
        """Safe-save the vault; see module docstring for the flow.

        ``validator`` is called after the format guard and may raise (e.g.
        SchemaTooNewError) to veto the write before anything touches disk.
        """
        kp = self.kp
        fmt = self.format_info
        if not fmt.writable:
            raise UnsupportedFormatError(
                f"vault is KDBX {fmt.version[0]}.{fmt.version[1]} / {fmt.kdf}; "
                f"Accnary only writes KDBX {SUPPORTED_WRITE_VERSION[0]}."
                f"{SUPPORTED_WRITE_VERSION[1]} - file stays read-only"
            )
        if validator is not None:
            validator()

        with writer_lock(self.path):
            self._save_locked(kp)

    def _assert_unchanged(self) -> None:
        if file_sha256(self.path) != self._opened_hash:
            raise ConflictError(
                "vault file changed or vanished since it was opened "
                "(another Accnary/KeePassXC instance?) - reload before saving"
            )

    def _save_locked(self, kp) -> None:
        target = self.path
        self._assert_unchanged()
        tmp = temporary_path(target)
        bak = target.with_name(target.name + _BAK_SUFFIX)
        try:
            # A stream avoids pykeepass's with_suffix('.tmp'), which collapses
            # distinct PID filenames into the same intermediate filename.
            with tmp.open("wb") as handle:
                kp.save(filename=handle)
                handle.flush()
                os.fsync(handle.fileno())
            self._verify_temp(tmp)
            self._assert_unchanged()
            if target.exists():
                copy_snapshot(target, bak)
            self._assert_unchanged()
            committed_hash = file_sha256(tmp)
            os.replace(tmp, target)
        except (ConflictError, UnsupportedFormatError):
            _unlink(tmp)
            raise
        except Exception as exc:
            _unlink(tmp)
            raise SafeSaveError(
                f"save failed before commit ({type(exc).__name__}); reload or retry"
            ) from exc
        self._opened_hash = committed_hash

    def _verify_temp(self, tmp: Path) -> None:
        """Re-open the freshly written temp file and compare structure."""
        try:
            check = PyKeePass(str(tmp), password=self.kp.password)
        except Exception as exc:
            raise SafeSaveError(f"temp file failed to re-open: {exc}") from exc
        want_entries = sorted(str(e.uuid) for e in self.kp.entries)
        got_entries = sorted(str(e.uuid) for e in check.entries)
        if want_entries != got_entries:
            raise SafeSaveError("entry set changed during save - refusing to replace")
        want_groups = sorted(g.name for g in self.kp.groups)
        got_groups = sorted(g.name for g in check.groups)
        if want_groups != got_groups:
            raise SafeSaveError("group structure changed during save - refusing to replace")
        if not same_contents(self.kp, check):
            raise SafeSaveError("vault content changed during save - refusing to replace")

    def change_master_password(self, new_password: str) -> None:
        kp = self.kp
        if not new_password:
            raise VaultError("master password must not be empty")
        old = kp.password
        kp.password = new_password
        try:
            self.save()
        except Exception:
            kp.password = old  # keep in-memory credentials consistent with disk
            raise

    # -- housekeeping ---------------------------------------------------------

    def _cleanup_stale_tmp(self) -> None:
        """Remove leftover temp files from interrupted saves of THIS vault."""
        for stale in self.path.parent.glob(self.path.name + _TMP_MARK + "*"):
            if stale.is_file():
                _unlink(stale)

    def __repr__(self) -> str:  # never include credentials
        state = "unlocked" if self._kp is not None else "locked"
        return f"KdbxVault({self.path.name!r}, {state})"
