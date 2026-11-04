# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 23:06
# @Modified  : 2026-10-24 23:40
# @Python    : 3.14.9
# @Description: Windows advisory writer lock and same-directory encrypted staging helpers.
from contextlib import contextmanager
import hashlib
import msvcrt
import os
from pathlib import Path
import shutil
import tempfile

from app.errors import ConflictError


@contextmanager
def writer_lock(target: Path):
    """Coordinate Accnary writers; OS releases the byte lock after a crash.

    The persistent .lock file contains only a zero byte. Do not unlink it:
    replacing lock files can let two processes lock different file objects.
    External editors do not participate; callers must also recheck hashes.
    """
    target = target.resolve()
    with target.with_name(target.name + ".lock").open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise ConflictError("another Accnary operation is writing this vault; retry after reloading") from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def temporary_path(target: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        prefix=target.name + ".accnary-tmp-", suffix=".kdbx",
        dir=target.parent, delete=False,
    ) as handle:
        return Path(handle.name)


def flush_file(path: Path) -> None:
    with path.open("rb+") as handle:
        os.fsync(handle.fileno())


def copy_snapshot(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
) -> None:
    """Atomically copy one known encrypted-file version to a snapshot.

    Hash the source while copying, then verify the staged bytes independently.
    The caller checks the source again before committing its main operation.
    """
    tmp = temporary_path(destination)
    try:
        source_digest = hashlib.sha256()
        with source.open("rb") as source_handle, tmp.open("wb") as target_handle:
            for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                source_digest.update(chunk)
                target_handle.write(chunk)
            target_handle.flush()
            os.fsync(target_handle.fileno())

        if source_digest.hexdigest() != expected_sha256:
            raise ConflictError(
                "vault file changed while its safety snapshot was being copied; "
                "reload before saving"
            )

        shutil.copystat(source, tmp)
        snapshot_digest = hashlib.sha256()
        with tmp.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                snapshot_digest.update(chunk)
        if snapshot_digest.hexdigest() != expected_sha256:
            raise OSError("encrypted snapshot changed during copying")
        os.replace(tmp, destination)
    finally:
        tmp.unlink(missing_ok=True)


def same_contents(left, right) -> bool:
    """Compare decrypted XML (including history) and attachment binaries in RAM."""
    from lxml import etree
    return (etree.tostring(left.tree, method="c14n") == etree.tostring(right.tree, method="c14n")
            and left.binaries == right.binaries)
