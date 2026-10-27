# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-27 11:12
# @Modified  : 2026-10-27 11:26
# @Python    : 3.14.9
# @Description: Accnary ToolHub update parsing and local preference regression checks.

import json
from pathlib import Path

import pytest

from app.services.update_service import (
    UpdateChecker,
    is_newer_version,
    parse_manifest_json,
)
from app.ui.settings import app_settings
from app.ui.settings_dialog import SettingsDialog


def test_update_checker_uses_the_existing_ini_preferences(monkeypatch, tmp_path):
    settings_dir = tmp_path / "prefs"
    monkeypatch.setenv("ACCNARY_SETTINGS_DIR", str(settings_dir))

    settings = UpdateChecker._settings()
    assert Path(settings.fileName()) == settings_dir / "Accnary.ini"
    settings.setValue("update/auto_check", False)
    settings.setValue("update/last_check_at", "2026-10-27T10:00:00")
    settings.sync()

    contents = (settings_dir / "Accnary.ini").read_text(encoding="utf-8")
    assert "[update]" in contents
    assert "auto_check=false" in contents
    assert "last_check_at=2026-10-27T10:00:00" in contents


def test_settings_dialog_defaults_to_auto_check_and_persists_opt_out(qapp):
    app_settings().clear()
    dialog = SettingsDialog()
    assert dialog.auto_update_checkbox.isChecked()

    dialog.auto_update_checkbox.setChecked(False)
    assert app_settings().value("update/auto_check", True, type=bool) is False
    dialog.close()


def test_toolhub_manifest_parser_and_semver_comparison():
    manifest = {
        "schema_version": 1,
        "apps": {
            "accnary": {
                "version": "0.2.0",
                "notes": "修复与改进",
                "asset": {
                    "url": "https://cnb.cool/oakun/ToolHub/-/releases/download/accnary-v0.2.0/Accnary.exe",
                    "sha256": "a" * 64,
                },
            }
        },
    }
    info = parse_manifest_json(json.dumps(manifest, ensure_ascii=False), "accnary")

    assert info is not None
    assert info.remote_version == "0.2.0"
    assert info.notes == "修复与改进"
    assert info.remote_sha256 == "a" * 64
    assert is_newer_version(info.remote_version, "0.1.0")

    manifest["apps"]["accnary"]["asset"]["url"] = "http://example.test/Accnary.exe"
    with pytest.raises(ValueError, match="HTTPS"):
        parse_manifest_json(json.dumps(manifest), "accnary")
