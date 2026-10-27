# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-25 11:15
# @Modified  : 2026-10-27 11:15
# @Python    : 3.14.9
# @Description: Workspace UI boundaries, virtual rows, responsive details and navigation wiring.
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QMenu, QPushButton, QStatusBar, QToolButton

from app.models import Account, Service
from app.ui.account_editor import AccountEditor
from app.ui.account_list import AccountDelegate, public_summary, summary_role
from app.ui.detail_panel import DetailPanel
from app.ui.main_window import MainWindow
from app.ui.widgets import CopyRow, SecretRow
from app.ui.settings import app_settings
from app.ui.settings_dialog import SettingsDialog


def test_compact_header_and_more_menu_keep_utilities_reachable(catalog, qapp, monkeypatch):
    called = []
    monkeypatch.setattr(MainWindow, "_open_backups", lambda self: called.append("backup"))
    monkeypatch.setattr(MainWindow, "_open_recycle_bin", lambda self: called.append("recycle"))
    window = MainWindow(catalog)
    window.resize(1220, 850)
    window._update_responsive()
    assert not window.lock_button.isHidden()
    assert not window.more_button.isHidden()
    assert window.findChild(QStatusBar) is None
    assert window.new_button.defaultAction() is window.new_action
    assert [action.text() for action in window.more_menu.actions() if not action.isSeparator()] == [
        "回收站", "备份与恢复", "检查更新", "设置"]
    window.backup_action.trigger()
    window.recycle_action.trigger()
    assert called == ["backup", "recycle"]
    assert window.nav_list.item(0).text() == "全部账户"
    window.close()


def test_many_rows_use_one_delegate_without_per_record_widgets(catalog, qapp):
    service = catalog.catalog.services[0]
    service.accounts.extend(Account(uuid=f"virtual-{i}", alias="虚构", username=f"user-{i}", password="do-not-display")
                            for i in range(2500))
    window = MainWindow(catalog)
    assert window.account_list.count() == 2501
    assert isinstance(window.account_list.itemDelegate(), AccountDelegate)
    assert window.account_list.itemWidget(window.account_list.item(2500)) is None
    assert "do-not-display" not in str(window.account_list.item(2500).data(summary_role))
    assert len(window.account_list.findChildren(QLabel)) == 0
    # In-memory display fixture only, remove before normal close's safety save.
    service.accounts[:] = service.accounts[:1]
    window.close()


def test_detail_commands_and_multiple_urls_are_visible(catalog, qapp):
    service = catalog.catalog.services[0]
    account = service.accounts[0]
    service.urls += ["https://alternate.example.invalid/portal"]
    service.login_urls = ["https://login.example.invalid/"]
    panel = DetailPanel(catalog)
    panel.show_account(service, account)
    urls = [row._value for row in panel.findChildren(CopyRow)]
    assert account.primary_url in urls and service.urls[-1] in urls and service.login_urls[0] in urls
    events = []
    panel.edit_requested.connect(lambda: events.append("edit"))
    panel.delete_requested.connect(lambda: events.append("delete"))
    panel.findChild(QToolButton, "editAccount").click()
    menu = panel.findChildren(QMenu)[0]
    menu.actions()[0].trigger()
    assert events == ["edit", "delete"]


def test_detail_reading_column_expands_and_shrinks_with_pane(catalog, qapp):
    panel = DetailPanel(catalog)
    panel.resize(704, 700)
    panel.show()
    qapp.processEvents()
    assert 600 <= panel._content.width() <= 616

    panel.resize(420, 700)
    qapp.processEvents()
    assert panel._content.width() < 616
    assert panel._content.width() <= panel._scroll.viewport().width()
    panel.close()


def test_no_empty_credentials_or_sections_for_passwordless_account(catalog, qapp):
    panel = DetailPanel(catalog)
    panel.show_account(Service(name="微信"), Account(alias="日常使用"))
    text = " ".join(label.text() for label in panel.findChildren(QLabel))
    assert "微信" in text
    assert "登录凭据" not in text and "邮箱与手机" not in text and "付费授权" not in text
    assert panel.findChildren(SecretRow) == []


def test_selection_and_theme_switch_remask_previous_secret(catalog, qapp):
    window = MainWindow(catalog)
    old = window.detail_panel.findChildren(SecretRow)[0]
    old._toggle()
    assert old._revealed
    window._toggle_theme()
    assert old._value == ""
    assert all(not row._revealed for row in window.detail_panel.findChildren(SecretRow))
    window.account_list.setCurrentRow(-1)
    assert window._selected_pair() is None
    assert window.detail_panel._current_uuid is None
    window.close()


def test_editor_groups_are_reachable_and_cancel_is_unchanged(catalog, qapp):
    fresh = AccountEditor(catalog)
    assert fresh.service_combo.currentText() == ""
    assert fresh.service_type_combo.currentData() == "website"
    fresh.reject()
    before = catalog.catalog.all_accounts()[0].username
    editor = AccountEditor(catalog, catalog.catalog.services[0], catalog.catalog.all_accounts()[0])
    assert [editor.tabs.tabText(i) for i in range(editor.tabs.count())] == [
        "基本资料", "平台与联系", "登录与绑定", "许可证", "自定义"]
    editor.username_edit.setText("cancel-this-draft")
    for index in range(editor.tabs.count()):
        editor.tabs.setCurrentIndex(index)
    editor.reject()
    assert catalog.catalog.all_accounts()[0].username == before


def test_free_text_url_does_not_break_list_rendering(qapp):
    service = Service(name="长标题" * 100, urls=["https://[unfinished"])
    assert public_summary(service, Account(username="fictional"))[0] == service.name


def test_more_menu_opens_settings_dialog_and_applies_existing_preferences(catalog, qapp):
    from app.ui import theme
    theme.apply_theme(qapp, "light")
    window = MainWindow(catalog)
    def choose():
        dialog = window.findChild(SettingsDialog)
        assert dialog is not None and dialog.isVisible()
        dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
        dialog.idle_combo.setCurrentIndex(dialog.idle_combo.findData(5))
        dialog.accept()
    QTimer.singleShot(0, choose)
    window.settings_action.trigger()
    assert theme.current_theme() == "dark"
    assert app_settings().value("theme") == "dark"
    assert int(app_settings().value("idle_lock_minutes")) == 5
    window._set_theme("light")
    window.close()


def test_removing_favorite_ui_preserves_old_flag_through_editor_save(catalog, qapp):
    from app.services import CatalogService
    from .conftest import TEST_PASSWORD
    account = catalog.catalog.all_accounts()[0]
    catalog.set_favorite(account.uuid, True)
    catalog.save()
    editor = AccountEditor(catalog, catalog.catalog.services[0], account)
    editor.username_edit.setText("edited-with-legacy-favorite")
    editor._on_accept()
    reopened = CatalogService.open(catalog.path, TEST_PASSWORD)
    assert reopened.catalog.all_accounts()[0].favorite is True
    window = MainWindow(reopened)
    assert "收藏" not in [window.nav_list.item(i).text() for i in range(window.nav_list.count())]
    assert window.findChild(QStatusBar) is None
    assert "收藏" not in " ".join(button.text() for button in window.detail_panel.findChildren(QPushButton))
    assert len(window.account_list.item(0).data(summary_role)) == 4
    window.close()
