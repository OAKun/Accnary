"""Phase 1 T2: vault lifecycle - create/unlock/lock/password rotation,
plus clean failure on missing, wrong-credential, and corrupted files."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import (
    BadCredentialsError,
    SafeSaveError,
    VaultError,
    VaultFormatError,
    VaultLockedError,
    VaultNotFoundError,
)
from app.storage import KdbxVault

from .conftest import TEST_PASSWORD


def test_create_unlock_lock_cycle(vault_path):
    vault = KdbxVault.create(vault_path, TEST_PASSWORD)
    assert vault.format_info.version == (4, 0)
    assert vault.format_info.kdf == "argon2"
    assert vault.format_info.cipher == "aes256"

    vault.lock()
    assert vault.is_locked
    with pytest.raises(VaultLockedError):
        _ = vault.kp
    with pytest.raises(VaultLockedError):
        _ = vault.format_info

    reopened = KdbxVault.unlock(vault_path, TEST_PASSWORD)
    assert not reopened.is_locked


def test_create_refuses_existing_file(vault_path):
    KdbxVault.create(vault_path, TEST_PASSWORD)
    with pytest.raises(VaultError):
        KdbxVault.create(vault_path, TEST_PASSWORD)


def test_unlock_missing_file(vault_path):
    with pytest.raises(VaultNotFoundError):
        KdbxVault.unlock(vault_path, TEST_PASSWORD)


def test_unlock_wrong_password(vault_path):
    KdbxVault.create(vault_path, TEST_PASSWORD)
    with pytest.raises(BadCredentialsError):
        KdbxVault.unlock(vault_path, "wrong-pass")


def test_corrupt_file_detected_and_left_untouched(vault_path):
    vault = KdbxVault.create(vault_path, TEST_PASSWORD)
    vault.lock()
    original = Path(vault_path).read_bytes()
    truncated = original[: len(original) // 2]
    Path(vault_path).write_bytes(truncated)

    with pytest.raises(VaultFormatError):
        KdbxVault.unlock(vault_path, TEST_PASSWORD)
    # the failed open must not "repair" or rewrite anything
    assert Path(vault_path).read_bytes() == truncated


def test_master_password_rotation(vault_path):
    vault = KdbxVault.create(vault_path, TEST_PASSWORD)
    vault.change_master_password("rotated-pass-2")

    with pytest.raises(BadCredentialsError):
        KdbxVault.unlock(vault_path, TEST_PASSWORD)
    reopened = KdbxVault.unlock(vault_path, "rotated-pass-2")
    assert reopened.kp.password == "rotated-pass-2"


def test_master_password_rotation_failure_rolls_back(vault_path, monkeypatch):
    vault = KdbxVault.create(vault_path, TEST_PASSWORD)

    def boom(*args, **kwargs):
        raise OSError("simulated I/O failure")

    monkeypatch.setattr("app.storage.vault.os.replace", boom)
    with pytest.raises(SafeSaveError):
        vault.change_master_password("never-applied-pass")

    # in-memory credentials must match what is actually on disk
    assert vault.kp.password == TEST_PASSWORD
    KdbxVault.unlock(vault_path, TEST_PASSWORD)  # old password still valid
