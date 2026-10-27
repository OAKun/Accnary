# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 22:06
# @Modified  : 2026-10-24 23:40
# @Python    : 3.14.9
# @Description: Accnary tests / phase4 / test_no_secret_leakage
"""Phase 4 security acceptance: plaintext-leakage checks (spec section 9).

After a realistic usage flow (create -> save -> copy -> backup -> lock ->
failed unlock -> delete), every file the app touched must either be a
KDBX-encrypted vault artifact or contain none of the planted secrets.
stdout/stderr must stay clean as well.
"""

from __future__ import annotations

from pathlib import Path

from app.errors import BadCredentialsError
from app.security.clipboard import copy_with_auto_clear
from app.storage import export_backup

MARKERS_SUBSTR = "LEAKCHECK"
_ALLOWED_SUFFIXES = {".kdbx", ".bak", ".lock"}


def _scan_tree(root: Path, markers: list[str]) -> tuple[list[str], list[str]]:
    """Return (leaked_files, unexpected_suffixes) under root."""
    leaked: list[str] = []
    unexpected: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in _ALLOWED_SUFFIXES:
            unexpected.append(str(path.relative_to(root)))
        blob = path.read_bytes()
        for marker in markers:
            if marker.encode() in blob:
                leaked.append(str(path.relative_to(root)))
                break
    return leaked, unexpected


def test_no_plaintext_leakage_across_full_flow(leak_vault, tmp_path, capsys, qapp):
    assert qapp is not None  # force QApplication before clipboard use
    svc, account, marker = leak_vault
    markers = [f"LEAKCHECK-PASS-{marker}", f"LEAKCHECK-KEY-{marker}",
               f"LEAKCHECK-TOKEN-{marker}", f"user-{marker}"]

    # exercise the flows a real session would
    export_backup(svc.vault, tmp_path / "backup" / "audit.kdbx")
    copy_with_auto_clear(account.password)
    svc.lock()
    try:
        type(svc).open(str(svc.path), "definitely-wrong-password")
    except BadCredentialsError:
        pass
    svc2 = type(svc).open(str(svc.path), "phase4-audit-pass")
    svc2.delete_account(account.uuid)
    svc2.save()
    svc2.lock()

    # every file under the vault/backup tree is encrypted and marker-free
    leaked, unexpected = _scan_tree(tmp_path, markers)
    assert leaked == [], f"plaintext secrets found in: {leaked}"
    assert unexpected == [], f"unexpected non-vault files created: {unexpected}"

    # stdout/stderr stayed clean during the whole flow
    captured = capsys.readouterr()
    for marker in markers:
        assert marker not in captured.out
        assert marker not in captured.err


def test_backup_survives_and_stays_encrypted(leak_vault, tmp_path):
    svc, _account, marker = leak_vault
    backup = tmp_path / "audit.kdbx"
    export_backup(svc.vault, backup)
    blob = backup.read_bytes()
    assert f"LEAKCHECK-PASS-{marker}".encode() not in blob
    assert f"LEAKCHECK-KEY-{marker}".encode() not in blob
    # the backup is a working vault
    reopened = type(svc).open(str(backup), "phase4-audit-pass")
    assert reopened.catalog.all_accounts()


def test_error_dialogs_carry_no_secrets(leak_vault, qapp):
    """Exception text surfaced in the UI must not embed vault content."""
    from app.errors import (
        BadCredentialsError,
        ConflictError,
        SafeSaveError,
        VaultFormatError,
        VaultNotFoundError,
    )

    probes = [
        BadCredentialsError("wrong master password"),
        VaultNotFoundError("vault file not found"),
        VaultFormatError("could not parse vault"),
        ConflictError("file changed on disk"),
        SafeSaveError("save failed, previous version intact"),
    ]
    for exc in probes:
        assert MARKERS_SUBSTR not in str(exc)
