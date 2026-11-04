# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-27 11:12
# @Modified  : 2026-10-27 11:26
# @Python    : 3.14.9
# @Description: Accnary ToolHub update parsing and local preference regression checks.

import json
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer, QUrl

from app.services import update_service
from app.services.update_service import (
    UpdateChecker,
    UpdateDownloader,
    is_newer_version,
    parse_manifest_json,
)
from app.ui.settings import app_settings
from app.ui.settings_dialog import SettingsDialog


@pytest.mark.parametrize("extra_bytes, expected", [(0, "current"), (1, "update")])
def test_manifest_limit_allows_exact_size_and_falls_back(
    qapp, tmp_path, monkeypatch, extra_bytes, expected,
):
    primary = tmp_path / "primary.json"
    backup = tmp_path / "backup.json"
    body = b'{"schema_version":1,"apps":{}}'
    primary.write_bytes(body.ljust(1024 * 1024 + extra_bytes))
    backup.write_text(json.dumps({
        "schema_version": 1,
        "apps": {"accnary": {"version": "2.0.0", "asset": {
            "url": "https://example.test/Accnary.exe", "sha256": "a" * 64,
        }}},
    }), encoding="utf-8")
    monkeypatch.setattr(update_service, "manifest_urls", [
        QUrl.fromLocalFile(str(path)).toString() for path in (primary, backup)
    ])
    monkeypatch.delenv(update_service.manifest_urls_env_name, raising=False)
    checker = UpdateChecker()
    loop = QEventLoop()
    outcomes = []

    def finish(outcome):
        outcomes.append(outcome)
        loop.quit()

    checker.no_update.connect(lambda _: finish("current"))
    checker.update_available.connect(lambda _: finish("update"))
    checker.check_failed.connect(lambda _: finish("failed"))
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: finish("timeout"))
    timer.start(5000)
    checker.check("1.0.0", manual=True)
    if not outcomes:
        loop.exec()
    timer.stop()
    checker.deleteLater()
    assert outcomes == [expected]


@pytest.mark.parametrize("aware", [False, True])
@pytest.mark.parametrize("age_hours, expected", [(1, False), (25, True), (-48, True)])
def test_auto_check_handles_legacy_offset_and_future_times(qapp, aware, age_hours, expected):
    now = datetime.now(timezone(timedelta(hours=8))) if aware else datetime.now()
    settings = UpdateChecker._settings()
    settings.setValue("update/last_check_at", (now - timedelta(hours=age_hours)).isoformat())
    checker = UpdateChecker()
    assert checker._auto_check_due() is expected
    checker.deleteLater()


def test_completed_check_records_timezone_and_throttles_next_check(qapp):
    checker = UpdateChecker()
    checker._mark_check_completed()
    saved = UpdateChecker._settings().value("update/last_check_at", "", type=str)
    assert datetime.fromisoformat(saved).utcoffset() is not None
    assert not checker._auto_check_due()
    checker.deleteLater()


def _download_local(qapp, source, destination, expected_hash, *, cancel=False):
    downloader = UpdateDownloader()
    loop = QEventLoop()
    outcomes = []

    def finish(kind, value=None):
        outcomes.append((kind, value))
        loop.quit()

    downloader.failed.connect(lambda message: finish("failed", message))
    downloader.completed.connect(lambda path: finish("completed", path))
    downloader.cancelled.connect(lambda: finish("cancelled"))
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: finish("timeout"))
    timer.start(5000)
    downloader.start(QUrl.fromLocalFile(str(source)).toString(), destination, expected_hash)
    if cancel:
        downloader.cancel()
    if not outcomes:
        loop.exec()
    timer.stop()
    assert not downloader.is_running
    downloader.deleteLater()
    assert len(outcomes) == 1
    return outcomes[0][0]


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["hash", "empty", "missing"])
def test_failed_download_preserves_existing_destination(qapp, tmp_path, existing, failure):
    source = tmp_path / "source.exe"
    destination = tmp_path / "destination.exe"
    if failure != "missing":
        source.write_bytes(b"" if failure == "empty" else b"fictional new executable")
    if existing:
        destination.write_bytes(b"previous executable")
    assert _download_local(qapp, source, destination, "0" * 64) == "failed"
    if existing:
        assert destination.read_bytes() == b"previous executable"
    else:
        assert not destination.exists()


def test_successful_download_replaces_destination_after_verification(qapp, tmp_path):
    source = tmp_path / "source.exe"
    destination = tmp_path / "destination.exe"
    payload = b"fictional verified executable"
    source.write_bytes(payload)
    destination.write_bytes(b"previous executable")
    assert _download_local(qapp, source, destination, hashlib.sha256(payload).hexdigest()) == "completed"
    assert destination.read_bytes() == payload


def test_cancelled_download_preserves_existing_destination(qapp, tmp_path):
    source = tmp_path / "source.exe"
    destination = tmp_path / "destination.exe"
    source.write_bytes(b"fictional new executable")
    destination.write_bytes(b"previous executable")
    assert _download_local(qapp, source, destination, "0" * 64, cancel=True) == "cancelled"
    assert destination.read_bytes() == b"previous executable"


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
