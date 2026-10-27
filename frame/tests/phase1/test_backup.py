"""Phase 1 T4: encrypted backup export/restore."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import BackupError
from app.models import Account
from app.services import CatalogService
from app.storage import export_backup, restore_from_backup

from .conftest import TEST_PASSWORD


def test_export_backup_is_encrypted_and_verifiable(full_catalog, tmp_path):
    svc, _account = full_catalog
    dest = tmp_path / "backups" / "vault-backup.kdbx"
    result = export_backup(svc.vault, dest)
    assert result == dest and dest.is_file()

    blob = dest.read_bytes()
    for secret in (b"demo-pw-1", b"TEST-KEY-0000-1111", b"demo-user"):
        assert secret not in blob, "backup must stay encrypted at rest"

    reopened = CatalogService.open(str(dest), TEST_PASSWORD)
    assert {a.username for a in reopened.catalog.all_accounts()} == {"demo-user"}


def test_restore_requires_explicit_confirmation(full_catalog, tmp_path):
    svc, _account = full_catalog
    dest = export_backup(svc.vault, tmp_path / "b.kdbx")
    with pytest.raises(BackupError):
        restore_from_backup(svc.path, dest, TEST_PASSWORD)  # no confirmed=True


def test_restore_recovers_deleted_account(full_catalog, tmp_path):
    svc, account = full_catalog
    dest = export_backup(svc.vault, tmp_path / "b.kdbx")

    svc.delete_account(account.uuid)
    svc.save()
    assert svc.catalog.all_accounts() == []

    restored_vault = restore_from_backup(svc.path, dest, TEST_PASSWORD, confirmed=True)
    restored = CatalogService(restored_vault)
    names = {a.username for a in restored.catalog.all_accounts()}
    assert names == {"demo-user"}
    assert Path(str(svc.path) + ".pre-restore.bak").is_file()

    # the restored handle is a fully working catalog
    target = restored.catalog.all_accounts()[0]
    assert target.license.license_key == "TEST-KEY-0000-1111"
    restored.set_favorite(target.uuid, True)
    restored.save()
    again = CatalogService.open(str(restored.path), TEST_PASSWORD)
    assert again.catalog.all_accounts()[0].favorite is True


def test_restore_rejects_wrong_password(full_catalog, tmp_path):
    svc, _account = full_catalog
    dest = export_backup(svc.vault, tmp_path / "b.kdbx")
    with pytest.raises(BackupError):
        restore_from_backup(svc.path, dest, "wrong-pass", confirmed=True)
    # current vault untouched
    assert CatalogService.open(str(svc.path), TEST_PASSWORD).catalog.services


def test_restore_missing_backup_fails(full_catalog, tmp_path):
    svc, _account = full_catalog
    with pytest.raises(BackupError):
        restore_from_backup(svc.path, tmp_path / "nope.kdbx", TEST_PASSWORD, confirmed=True)


def test_add_account_after_backup_flow(full_catalog, tmp_path):
    """Backup -> mutate -> restore returns to the exact backup state."""
    svc, account = full_catalog
    dest = export_backup(svc.vault, tmp_path / "b.kdbx")

    service = svc.catalog.services[0]
    svc.add_account(service, Account(username="extra-user"))
    svc.save()
    assert len(svc.catalog.all_accounts()) == 2

    restored = CatalogService(
        restore_from_backup(svc.path, dest, TEST_PASSWORD, confirmed=True)
    )
    assert {a.username for a in restored.catalog.all_accounts()} == {"demo-user"}
