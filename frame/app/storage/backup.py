# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 14:52
# @Modified  : 2026-10-24 23:40
# @Python    : 3.14.9
# @Description: Accnary app / storage / backup
"""Encrypted backup export and restore.

The KDBX file is encrypted at rest, so a backup IS a byte copy - no plaintext
intermediate ever exists. Every backup is verified by re-opening it with the
current credentials before being declared good.
"""

from __future__ import annotations

import shutil
import os
from pathlib import Path

from pykeepass import PyKeePass

from app.errors import BackupError
from app.storage.vault import KdbxVault, file_sha256
from app.storage.atomic import copy_snapshot, flush_file, same_contents, temporary_path, writer_lock


def export_backup(vault: KdbxVault, dest_path: str | Path) -> Path:
    """Copy the (encrypted) vault file to ``dest_path`` and verify the copy.

    The destination keeps full KDBX encryption; never export to a location
    you do not trust with the whole vault.
    """
    kp = vault.kp  # raises VaultLockedError when locked
    source = vault.path
    if not source.is_file():
        raise BackupError(f"vault file vanished: {source}")
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == dest.resolve() or (dest.exists() and source.samefile(dest)):
        raise BackupError("backup destination must differ from the vault")
    tmp = temporary_path(dest)
    try:
        with writer_lock(source), writer_lock(dest):
            vault._assert_unchanged()
            shutil.copy2(source, tmp)
            flush_file(tmp)
            check = PyKeePass(str(tmp), password=kp.password)
            if not same_contents(kp, check):
                raise BackupError("backup does not match the saved vault; save pending edits first")
            vault._assert_unchanged()
            os.replace(tmp, dest)
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError(f"backup failed ({type(exc).__name__}); previous destination retained") from exc
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def restore_from_backup(
    vault_path: str | Path,
    backup_path: str | Path,
    password: str,
    *,
    confirmed: bool = False,
) -> KdbxVault:
    """Replace the vault file with a backup and re-open it.

    Requires ``confirmed=True`` - restoring overwrites the current vault, so
    the caller must prove the user explicitly asked for it. A safety snapshot
    of the pre-restore state is kept as ``<vault>.pre-restore.bak``.
    """
    if not confirmed:
        raise BackupError(
            "restore overwrites the current vault; call with confirmed=True "
            "only after the user explicitly confirmed"
        )
    backup = Path(backup_path)
    target = Path(vault_path)
    if not backup.is_file():
        raise BackupError(f"backup file not found: {backup}")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.resolve() == backup.resolve() or (target.exists() and target.samefile(backup)):
        raise BackupError("backup and restore target must be different files")
    with writer_lock(target):
        before_hash = file_sha256(target)
        tmp = temporary_path(target)
        try:
            # Validate precisely the encrypted bytes that will be committed.
            shutil.copy2(backup, tmp)
            flush_file(tmp)
            check = PyKeePass(str(tmp), password=password)
            if file_sha256(target) != before_hash:
                raise BackupError("restore target changed during validation")
            if target.exists():
                safety = target.with_name(target.name + ".pre-restore.bak")
                copy_snapshot(target, safety)
            if file_sha256(target) != before_hash:
                raise BackupError("restore target changed before replacement")
            os.replace(tmp, target)
        except Exception as exc:
            raise BackupError(f"restore failed ({type(exc).__name__}); current vault was not replaced") from exc
        finally:
            tmp.unlink(missing_ok=True)
    vault = KdbxVault.unlock(target, password)
    if not same_contents(check, vault.kp):
        raise BackupError("restored vault changed after replacement; safety snapshot is retained")
    del password
    return vault
