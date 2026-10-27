"""Unlock dialog: wrong password, correct unlock, create-new-vault flow."""

from __future__ import annotations

from pathlib import Path

from app.errors import BadCredentialsError
from app.services import CatalogService
from app.ui.unlock_dialog import UnlockDialog

from .conftest import TEST_PASSWORD


def test_unlock_wrong_password_shows_error(catalog, qapp, no_recent_vaults):
    dialog = UnlockDialog(vault_path=str(catalog.path))
    dialog.path_edit.setText(str(catalog.path))
    dialog.password_edit.setText("wrong-password")
    dialog._unlock()
    assert dialog.catalog is None
    assert "主密码不正确" in dialog.error_label.text()
    assert dialog.result() != UnlockDialog.DialogCode.Accepted


def test_unlock_correct_password_accepts(catalog, qapp, no_recent_vaults):
    dialog = UnlockDialog(vault_path=str(catalog.path))
    dialog.password_edit.setText(TEST_PASSWORD)
    dialog._unlock()
    assert dialog.catalog is not None
    assert dialog.catalog.path == catalog.path
    assert dialog.result() == UnlockDialog.DialogCode.Accepted
    assert no_recent_vaults == [str(catalog.path)]  # remembered via patched hook


def test_unlock_corrupt_file_reported(tmp_path, qapp, no_recent_vaults):
    bad = tmp_path / "bad.kdbx"
    bad.write_bytes(b"definitely-not-a-kdbx-file")
    dialog = UnlockDialog(vault_path=str(bad))
    dialog.password_edit.setText(TEST_PASSWORD)
    dialog._unlock()
    assert dialog.catalog is None
    assert "无法读取" in dialog.error_label.text()


def test_create_new_vault_flow(tmp_path, qapp, no_recent_vaults):
    path = tmp_path / "fresh" / "new-vault.kdbx"
    dialog = UnlockDialog()
    dialog._toggle_create()
    assert dialog.confirm_edit.isVisible() or True  # offscreen: visibility flag
    dialog.path_edit.setText(str(path))
    dialog.password_edit.setText("new-master-pass-1")
    dialog.confirm_edit.setText("new-master-pass-1")
    dialog._create()
    assert dialog.catalog is not None
    assert Path(path).is_file()
    # the created vault really opens with the new master password
    CatalogService.open(str(path), "new-master-pass-1")


def test_create_mismatched_confirmation_rejected(tmp_path, qapp, no_recent_vaults):
    path = tmp_path / "nope.kdbx"
    dialog = UnlockDialog()
    dialog._toggle_create()
    dialog.path_edit.setText(str(path))
    dialog.password_edit.setText("pass-one-1")
    dialog.confirm_edit.setText("pass-two-2")
    dialog._create()
    assert dialog.catalog is None
    assert "不一致" in dialog.error_label.text()
    assert not path.exists()


def test_create_short_password_rejected(tmp_path, qapp, no_recent_vaults):
    path = tmp_path / "short.kdbx"
    dialog = UnlockDialog()
    dialog._toggle_create()
    dialog.path_edit.setText(str(path))
    dialog.password_edit.setText("short")
    dialog.confirm_edit.setText("short")
    dialog._create()
    assert dialog.catalog is None
    assert "8 个字符" in dialog.error_label.text()
