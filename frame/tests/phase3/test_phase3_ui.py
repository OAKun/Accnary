# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 21:35
# @Modified  : 2026-10-24 23:40
# @Python    : 3.14.9
# @Description: Accnary tests / phase3 / test_phase3_ui
"""Phase 3 T2: recent-use tracking, service attribute editing, recycle-bin
dialog, generator popup, and native guard degradation (offscreen)."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from app.errors import SafeSaveError
from app.models import Account, Service, ServiceType
from app.security.password_generator import (
    GeneratorPolicy,
    PasswordGeneratorError,
    generate_password,
)
from app.ui.main_window import _ActivityMonitor, SessionLockFilter
from app.ui.recycle_bin_dialog import RecycleBinDialog
from app.ui.widgets import GeneratorPopup

from .conftest import TEST_PASSWORD


# ---------------------------------------------------------------------------
# recent-use tracking
# ---------------------------------------------------------------------------

def test_mark_used_and_save_persists(search_catalog, qapp):
    svc, _nasa, nasa_account, _pan, _pan_account = search_catalog
    svc.mark_used_and_save(nasa_account.uuid)
    reopened = type(svc).open(str(svc.path), TEST_PASSWORD)
    account = next(a for a in reopened.catalog.all_accounts() if a.username == "researcher-1")
    assert account.last_used_at is not None
    # visible through the "最近使用" nav source
    recent = [a for a in reopened.catalog.services[0].accounts if a.last_used_at]
    assert [a.username for a in recent] == ["researcher-1"]


def test_mark_used_failure_keeps_vault_intact(search_catalog, qapp, monkeypatch):
    svc, _nasa, nasa_account, *_ = search_catalog

    def boom(_src, _dst):
        raise OSError("disk full")

    import app.storage.vault as vault_module

    monkeypatch.setattr(vault_module.os, "replace", boom)
    try:
        svc.mark_used_and_save(nasa_account.uuid)
        raised = False
    except SafeSaveError:
        raised = True
    assert raised
    # vault on disk still opens with the previous content
    reopened = type(svc).open(str(svc.path), TEST_PASSWORD)
    assert len(reopened.catalog.all_accounts()) == 2


# ---------------------------------------------------------------------------
# service attribute editing (platform info shared by all accounts)
# ---------------------------------------------------------------------------

def test_service_attrs_edit_rewrites_all_account_meta(search_catalog, qapp):
    svc, nasa, nasa_account, _pan, _pan_account = search_catalog
    nasa.type = ServiceType.OTHER
    nasa.category = "科研数据"
    nasa.tags = ["科研", "遥感", "新标签"]
    nasa.aliases = ["Earthdata"]
    nasa.urls = ["https://earthdata.nasa.gov/", "https://urs.earthdata.nasa.gov/"]
    svc.update_account(nasa_account)  # triggers meta rewrite of this entry
    svc.save()

    reopened = type(svc).open(str(svc.path), TEST_PASSWORD)
    loaded = reopened.catalog.services[0]
    assert loaded.category == "科研数据"
    assert "新标签" in loaded.tags and loaded.aliases == ["Earthdata"]
    assert len(loaded.urls) == 2
    # every account entry of the service carries the new service block
    for account in loaded.accounts:
        entry = reopened.vault.kp.find_entries(
            uuid=__import__("uuid").UUID(account.uuid), first=True
        )
        assert "新标签" in entry.custom_properties["Accnary.Meta"]
    # searchable right away (index rebuilt on save)
    assert any(h.service.name == "NASA Earthdata" for h in reopened.search_index.search("Earthdata"))


# ---------------------------------------------------------------------------
# recycle bin dialog
# ---------------------------------------------------------------------------

def test_recycle_bin_dialog_lists_and_restores(search_catalog, qapp):
    svc, _nasa, nasa_account, _pan, _pan_account = search_catalog
    svc.delete_account(nasa_account.uuid)
    svc.save()

    changed = {"count": 0}
    dialog = RecycleBinDialog(svc, on_changed=lambda: changed.__setitem__("count", changed["count"] + 1))
    assert dialog.list_widget.count() == 1
    assert "researcher-1" in dialog.list_widget.item(0).text()
    assert "NASA Earthdata" in dialog.list_widget.item(0).text()

    dialog.list_widget.setCurrentRow(0)
    dialog._restore()
    assert changed["count"] == 1
    assert dialog.list_widget.count() == 0  # back to empty after restore

    reopened = type(svc).open(str(svc.path), TEST_PASSWORD)
    assert {a.username for a in reopened.catalog.all_accounts()} == {"researcher-1", "pan-user"}


# ---------------------------------------------------------------------------
# generator popup + policy
# ---------------------------------------------------------------------------

def test_generator_popup_uses_policy(qapp):
    popup = GeneratorPopup()
    popup.length_spin.setValue(32)
    popup.special_check.setChecked(False)
    popup._regenerate()
    pwd = popup.preview_edit.text()
    assert len(pwd) == 32
    assert not any(c in "!@#$%^&*-_=?.)" for c in pwd)
    popup._use()
    assert popup.generated_password == pwd
    assert popup.result() == GeneratorPopup.DialogCode.Accepted


def test_generator_policy_error_shown(qapp):
    popup = GeneratorPopup()
    popup.upper_check.setChecked(False)
    popup.lower_check.setChecked(False)
    popup.digits_check.setChecked(False)
    popup.special_check.setChecked(False)
    popup.no_similar_check.setChecked(False)
    popup.exclude_edit.setText("a")
    popup._regenerate()  # custom_chars empty -> no pools at all
    assert popup.preview_edit.text() == ""


# ---------------------------------------------------------------------------
# native guard degradation (offscreen) + activity monitor
# ---------------------------------------------------------------------------

def test_native_filters_degrade_gracefully(qapp):
    session = SessionLockFilter(0)
    # offscreen / hwnd 0: registration must fail cleanly, filter stays inert
    session.nativeEventFilter(b"x", 0)
    session.shutdown()


def test_activity_monitor_tracks_events(qapp):
    from PySide6.QtCore import QEvent, QTimer

    monitor = _ActivityMonitor(qapp)
    before = monitor.idle_seconds()
    assert before >= 0
    # simulate a key event through the app filter
    from PySide6.QtCore import QObject

    event = QEvent(QEvent.Type.KeyPress)
    monitor.eventFilter(QObject(), event)
    after = monitor.idle_seconds()
    assert after <= before + 0.001


def test_idle_check_disabled_by_setting(search_catalog, qapp, monkeypatch):
    from app.ui.settings import app_settings

    svc, *_ = search_catalog
    main_window = None
    app_settings().setValue("idle_lock_minutes", 0)
    try:
        from app.ui.main_window import MainWindow

        main_window = MainWindow(svc)
        locked_calls = []
        monkeypatch.setattr(main_window, "lock_and_unlock", lambda: locked_calls.append(1))
        # force the idle path with an enormous idle time still below threshold=0?
        # with minutes=0 the check must return early regardless
        main_window._check_idle()
        assert locked_calls == []
    finally:
        if main_window is not None:
            main_window._closing_for_real = True
            main_window.close()
            app_settings().setValue("idle_lock_minutes", 10)
