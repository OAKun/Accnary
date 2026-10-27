"""Phase 1 T3: safe-save flow - .bak snapshot, temp cleanup, conflict
detection, and fault injection (rename failure / disk-full simulation)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pykeepass import PyKeePass

from app.errors import ConflictError, SafeSaveError
from app.models import Account
from app.services import CatalogService

from .conftest import TEST_PASSWORD


def _tmp_files(path: str) -> list[Path]:
    return list(Path(path).parent.glob(Path(path).name + ".accnary-tmp-*"))


def test_save_creates_bak_and_cleans_tmp(make_full_catalog):
    svc, first = make_full_catalog()
    path = str(svc.path)
    svc.save()  # first save already happened in fixture; snapshot now exists

    service = svc.catalog.services[0]
    svc.add_account(service, Account(username="second-user", password="pw2"))
    svc.save()

    bak = Path(path + ".bak")
    assert bak.is_file()
    assert _tmp_files(path) == [], "temp files must be cleaned after save"

    # .bak holds the state BEFORE the last save (no second account)
    bak_kp = PyKeePass(str(bak), password=TEST_PASSWORD)
    assert "second-user" not in {e.username for e in bak_kp.entries}

    # main file holds the new state
    reopened = CatalogService.open(path, TEST_PASSWORD)
    assert {a.username for a in reopened.catalog.all_accounts()} == {
        "demo-user",
        "second-user",
    }


def test_conflict_detected_when_file_changed_externally(vault_path):
    writer = CatalogService.create_vault(vault_path, TEST_PASSWORD)
    stale = CatalogService.open(vault_path, TEST_PASSWORD)

    # another instance saves while `stale` is open
    service = writer.add_service("External")
    writer.add_account(service, Account(username="external-user"))
    writer.save()

    hash_before = Path(vault_path).read_bytes()
    with pytest.raises(ConflictError):
        stale.save()
    # external content must be intact (not clobbered by the stale writer)
    assert Path(vault_path).read_bytes() == hash_before
    assert _tmp_files(vault_path) == []


def test_recover_from_conflict_via_reopen(vault_path):
    writer = CatalogService.create_vault(vault_path, TEST_PASSWORD)
    stale = CatalogService.open(vault_path, TEST_PASSWORD)
    service = writer.add_service("External")
    writer.add_account(service, Account(username="external-user"))
    writer.save()

    with pytest.raises(ConflictError):
        stale.save()

    stale.reopen()
    names = {a.username for a in stale.catalog.all_accounts()}
    assert "external-user" in names
    stale.set_favorite(next(iter(
        a.uuid for a in stale.catalog.all_accounts() if a.username == "external-user"
    )), True)
    stale.save()  # now succeeds on top of the external changes

    reopened = CatalogService.open(vault_path, TEST_PASSWORD)
    target = next(a for a in reopened.catalog.all_accounts() if a.username == "external-user")
    assert target.favorite is True


def test_rename_failure_keeps_previous_version(full_catalog, monkeypatch):
    svc, _account = full_catalog
    path = str(svc.path)
    before = Path(path).read_bytes()

    def boom(src, dst):
        raise PermissionError("simulated locked target file")

    monkeypatch.setattr("app.storage.vault.os.replace", boom)
    with pytest.raises(SafeSaveError):
        svc.save()

    assert Path(path).read_bytes() == before, "previous version must be intact"
    assert _tmp_files(path) == [], "temp file must be cleaned after failure"


def test_disk_full_during_temp_write_keeps_vault(full_catalog, monkeypatch):
    svc, _account = full_catalog
    path = str(svc.path)
    before = Path(path).read_bytes()

    def boom(self, filename=None):
        raise OSError(28, "No space left on device")  # ENOSPC

    monkeypatch.setattr(PyKeePass, "save", boom)
    with pytest.raises(SafeSaveError):
        svc.save()

    assert Path(path).read_bytes() == before
    assert _tmp_files(path) == []
    reopened = CatalogService.open(path, TEST_PASSWORD)
    assert reopened.catalog.services


def test_stale_tmp_files_removed_on_open(vault_path):
    CatalogService.create_vault(vault_path, TEST_PASSWORD)
    stale_tmp = Path(vault_path + ".accnary-tmp-999")
    stale_tmp.write_bytes(b"leftover from a crashed save")
    CatalogService.open(vault_path, TEST_PASSWORD)
    assert not stale_tmp.exists()


def test_no_plaintext_secrets_in_saved_file(full_catalog):
    svc, _account = full_catalog
    blob = Path(str(svc.path)).read_bytes()
    for secret in (b"demo-pw-1", b"TEST-KEY-0000-1111", b"wx_acc_01", b"demo-user"):
        assert secret not in blob, f"plaintext {secret!r} leaked into vault file"
