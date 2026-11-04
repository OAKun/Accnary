# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-25 11:14
# @Modified  : 2026-10-26 18:36
# @Python    : 3.14.9
# @Description: Main-window integration with delegate-backed public display roles.
"""Main window integration tests (offscreen, real storage layer)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QToolTip
import pytest

from app.models import Account
from app.services import CatalogService
from app.ui.main_window import MainWindow
from app.ui.account_editor import AccountEditor
from app.ui.recycle_bin_dialog import RecycleBinDialog
from app.ui.widgets import CopyRow

from .conftest import TEST_PASSWORD


def _row_texts(window: MainWindow) -> list[str]:
    return [window.account_list.item(i).text() for i in range(window.account_list.count())]


def test_equivalent_search_retains_list_item_and_detail(catalog, qapp):
    window = MainWindow(catalog)
    window.search_edit.setText("ui-user")
    item = window.account_list.currentItem()
    assert item is not None
    window.search_edit.setText(" UI-USER ")
    assert window.account_list.currentItem() is item
    window.search_edit.setText("does-not-match-987654")
    assert window.account_list.count() == 0
    window.close()


def test_lock_closes_dirty_editor_without_waiting_for_confirmation(catalog, qapp, monkeypatch):
    window = MainWindow(catalog)
    window.show()
    editor = AccountEditor(catalog, parent=window)
    editor.show()
    editor.password_input.edit.setText("fictional-unsaved-secret")
    qapp.processEvents()

    def unexpected_prompt(*args):
        raise AssertionError("locking must not wait for an editor confirmation")

    monkeypatch.setattr(QMessageBox, "question", unexpected_prompt)
    window.lock_and_unlock()
    assert not editor.isVisible()
    assert not editor.password_input.edit.text()
    assert catalog.is_locked
    window.close()


def test_create_selects_saved_account_without_reopening_vault(catalog, qapp, monkeypatch):
    window = MainWindow(catalog)
    panel = window.detail_panel
    window.search_edit.setText("nothing-matches-987654")

    def accept_editor(editor):
        editor.service_combo.setCurrentText("新平台")
        editor.username_edit.setText("fictional-new-account")
        editor._on_accept()
        return editor.result()

    def unexpected_reopen():
        raise AssertionError("successful save already refreshed the catalog")

    monkeypatch.setattr(AccountEditor, "exec", accept_editor)
    monkeypatch.setattr(catalog, "reopen", unexpected_reopen)
    window._new_account()
    assert window.search_edit.text() == ""
    assert window._selected_pair()[1].username == "fictional-new-account"
    assert window.detail_panel is panel
    reopened = CatalogService.open(catalog.path, TEST_PASSWORD)
    assert reopened.search_index.search("fictional-new-account")[0].account.uuid == window._selected_uuid()
    reopened.lock()
    window.close()


def test_copy_feedback_survives_recent_sort(catalog, qapp, monkeypatch):
    account = catalog.add_account("Z 示例平台", Account(username="fictional-copy"))
    copied = []
    monkeypatch.setattr("app.ui.widgets.copy_with_auto_clear", copied.append)
    window = MainWindow(catalog)
    other_item = window.account_list.item(0)
    window.account_list.setCurrentRow(1)
    assert window._selected_uuid() == account.uuid
    row = next(row for row in window.detail_panel.findChildren(CopyRow)
               if row.value_label.text() == account.username)
    row.copy_btn.click()
    assert copied == [account.username]
    assert window.account_list.currentRow() == 0
    assert window.account_list.item(1) is other_item
    assert window._selected_uuid() == account.uuid
    assert row.copy_btn.toolTip() == "已复制"
    row._copy_feedback_timer.start(0)
    qapp.processEvents()
    assert row.copy_btn.toolTip() == "复制账号"
    window.close()


def test_window_lists_accounts_and_shows_detail(catalog, qapp):
    window = MainWindow(catalog)
    assert window.account_list.count() == 1
    texts = _row_texts(window)[0]
    assert "UI云盘" in texts and "主账号" in texts and "ui-user" in texts

    # selection auto-populates the detail panel
    window.account_list.setCurrentRow(0)
    from PySide6.QtWidgets import QLabel as _QLabel

    detail = " ".join(
        lbl.text()
        for lbl in window.detail_panel._content.findChildren(_QLabel)
    )
    assert "凭据" in detail
    assert "ui-user" in detail
    assert "微信授权登录 · 微信主号" in detail
    window.close()


def test_recent_sort_keeps_legacy_favorite_data(catalog, qapp):
    window = MainWindow(catalog)
    account = catalog.catalog.all_accounts()[0]
    catalog.set_favorite(account.uuid, True)
    catalog.mark_used_and_save(account.uuid)
    service = catalog.catalog.services[0]
    catalog.add_account(service, Account(username="plain-user"))
    catalog.save()
    catalog.reopen()
    window._refresh_accounts()
    assert window.account_list.count() == 2
    assert window._selected_nav() == "全部账户"
    assert "ui-user" in window.account_list.item(0).text()
    assert "收藏" not in [window.nav_list.item(i).text() for i in range(window.nav_list.count())]
    assert "最近使用" not in [window.nav_list.item(i).text() for i in range(window.nav_list.count())]
    assert window.catalog.catalog.all_accounts()[0].favorite is True
    window.close()


def test_copy_updates_recent_use_without_synchronous_vault_write(
    catalog, qapp, monkeypatch
):
    window = MainWindow(catalog)
    account = catalog.catalog.all_accounts()[0]
    original_save = catalog.save
    saves = []

    def track_save():
        saves.append(True)
        original_save()

    monkeypatch.setattr(catalog, "save", track_save)
    window._on_credential_copied(account.uuid)

    assert saves == []
    assert account.last_used_at is not None
    assert catalog.has_unsaved_changes

    assert window.close()
    assert saves == [True]
    reopened = CatalogService.open(catalog.path, TEST_PASSWORD)
    assert reopened.catalog.all_accounts()[0].last_used_at == account.last_used_at


def test_nav_uses_unambiguous_legacy_purpose_and_hides_empty_categories(catalog, qapp):
    from app.models import ServiceType
    window = MainWindow(catalog)
    research = catalog.add_service("科研平台A", type=ServiceType.RESEARCH_PLATFORM)
    window._refresh_accounts()
    assert "科研与学术" not in [window.nav_list.item(i).text() for i in range(window.nav_list.count())]
    catalog.add_account(research, Account(username="research-user"))
    catalog.save()
    window.catalog.reopen()
    window._refresh_accounts()
    row = next(i for i in range(window.nav_list.count()) if window.nav_list.item(i).text() == "科研与学术")
    window.nav_list.setCurrentRow(row)
    assert window.account_list.count() == 1
    assert "research-user" in window.account_list.item(0).text()
    window.nav_list.setCurrentRow(0)
    assert window.account_list.count() == 2
    window.close()


@pytest.mark.parametrize("window_width", [535, 800, 860])
def test_category_switch_keeps_navigation_stable(catalog, qapp, window_width):
    window = MainWindow(catalog)
    window.resize(window_width, 640)
    window.show()
    qapp.processEvents()
    assert not window.sidebar.isVisible()

    window.nav_button.click()
    qapp.processEvents()
    assert window.sidebar.isVisible()
    splitter_sizes = window.splitter.sizes()
    assert splitter_sizes[0] == window.sidebar.minimumWidth()
    assert splitter_sizes[1] >= window.middle_pane.minimumWidth()
    if window_width == 800:
        assert splitter_sizes[2] == 0
    item = next(
        window.nav_list.item(row)
        for row in range(1, window.nav_list.count())
        if window.nav_list.item(row).text() != "账号分类"
    )
    assert item.toolTip() == ""
    position = window.nav_list.visualItemRect(item).center()
    global_position = window.nav_list.viewport().mapToGlobal(position)

    QTest.mouseClick(window.nav_list.viewport(), Qt.MouseButton.LeftButton, pos=position)
    qapp.processEvents()

    assert window._nav_open
    assert window.sidebar.isVisible()
    assert window.splitter.sizes() == splitter_sizes
    account_position = window.account_list.viewport().mapFromGlobal(global_position)
    assert window.account_list.itemAt(account_position) is None
    QTest.qWait(800)
    assert not QToolTip.isVisible()
    window.close()


def test_search_filters_accounts(catalog, qapp):
    window = MainWindow(catalog)
    service = window.catalog.catalog.services[0]
    window.catalog.add_account(service, Account(username="other-user"))
    window.catalog.save()
    window.catalog.reopen()
    window._refresh_accounts()
    assert window.account_list.count() == 2

    window.search_edit.setText("other-user")
    assert window.account_list.count() == 1
    assert "other-user" in _row_texts(window)[0]

    # search across identity labels too ("微信主号")
    window.search_edit.setText("微信主号")
    assert window.account_list.count() == 1
    window.search_edit.setText("")
    assert window.account_list.count() == 2
    window.close()


def test_delete_account_with_confirmed_box(catalog, qapp, monkeypatch):
    window = MainWindow(catalog)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    window._delete_selected()
    assert window.account_list.count() == 0

    reopened = CatalogService.open(str(catalog.path), TEST_PASSWORD)
    assert reopened.catalog.all_accounts() == []
    window.close()


def test_delete_keeps_adjacent_account_and_offers_recycle_bin(catalog, qapp, monkeypatch):
    removed = catalog.add_account("Y 示例平台", Account(username="fictional-deleted"))
    neighbor = catalog.add_account("Z 示例平台", Account(username="fictional-neighbor"))
    catalog.save()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    opened = []
    monkeypatch.setattr(RecycleBinDialog, "exec", lambda dialog: opened.append(dialog.list_widget.count()))
    window = MainWindow(catalog)
    window.resize(700, 560)
    window.show()
    qapp.processEvents()
    window.account_list.setCurrentRow(1)
    assert window._selected_uuid() == removed.uuid
    window._activate_detail()
    window._delete_selected()
    assert window.middle_pane.isVisible()
    assert window._selected_uuid() == neighbor.uuid
    assert window.recycle_notice.isVisible()
    window.open_recycle_button.click()
    assert opened == [1]
    assert not window.recycle_notice.isVisible()
    window.close()


def test_theme_toggle_updates_status(catalog, qapp):
    from app.ui import theme

    window = MainWindow(catalog)
    theme.apply_theme(qapp, "light")
    window._toggle_theme()
    assert theme.current_theme() == "dark"
    window._toggle_theme()
    assert theme.current_theme() == "light"
    window.close()


def test_search_shortcut_returns_from_narrow_detail_to_visible_search(catalog, qapp):
    window = MainWindow(catalog)
    window.resize(700, 560)
    window.show()
    qapp.processEvents()
    window.account_list.setCurrentRow(0)
    window._activate_detail()
    assert window._mobile_detail
    assert not window.middle_pane.isVisible()

    window._focus_search()
    qapp.processEvents()
    assert not window._mobile_detail
    assert window.middle_pane.isVisible()
    assert window.search_edit.isVisible()
    assert window.search_edit.hasFocus()
    window.close()


def test_narrow_search_keyboard_navigation_keeps_selected_account(catalog, qapp):
    window = MainWindow(catalog)
    window.resize(700, 560)
    window.show()
    window.search_edit.setText("ui-user")
    window.search_edit.setFocus()
    qapp.processEvents()
    selected = window.account_list.currentItem()
    assert selected is not None
    QTest.keyClick(window.search_edit, Qt.Key.Key_Down)
    assert window.account_list.hasFocus()
    window.search_edit.setFocus()
    QTest.keyClick(window.search_edit, Qt.Key.Key_Return)
    assert window._mobile_detail
    QTest.keyClick(window.back_button, Qt.Key.Key_Space)
    assert window.account_list.currentItem() is selected
    assert window.account_list.hasFocus()
    window.close()


def test_empty_search_action_clears_query_and_restores_accounts(catalog, qapp):
    window = MainWindow(catalog)
    window.show()
    window.search_edit.setText("no-such-account-987654")
    qapp.processEvents()
    assert window.account_list.count() == 0
    assert window.list_empty_action.isVisible()
    assert window.list_empty_action.text() == "清除搜索"
    QTest.mouseClick(window.list_empty_action, Qt.MouseButton.LeftButton)
    assert not window.search_edit.text()
    assert window.search_edit.hasFocus()
    assert window.account_list.count() == 1
    assert not window.list_empty_action.isVisible()
    window.close()


def test_clearing_search_restores_original_category_selection_and_scroll(catalog, qapp):
    service = catalog.catalog.services[0]
    original = service.accounts[:]
    service.accounts.extend(
        Account(uuid=f"preview-{index}", username=f"preview-user-{index:02d}")
        for index in range(48)
    )
    catalog.search_index.build(catalog.catalog)
    window = MainWindow(catalog)
    window.resize(1100, 540)
    window.show()
    QTest.qWait(80)
    window.nav_list.setCurrentRow(window.nav_list.count() - 1)
    category = window._selected_nav()
    assert category != window.nav_list.item(0).text()
    window.account_list.setCurrentRow(20)
    selected_uuid = window._selected_uuid()
    scrollbar = window.account_list.verticalScrollBar()
    scrollbar.setValue(15)
    assert scrollbar.value() == 15
    window.search_edit.setText("preview-user-47")
    assert window.account_list.count() == 1
    assert window._selected_uuid() != selected_uuid
    window.nav_list.setCurrentRow(0)
    window.search_edit.setText("nothing-matches-987654")
    window.list_empty_action.click()
    assert window._selected_nav() == category
    assert window._selected_uuid() == selected_uuid
    assert scrollbar.value() == 15
    service.accounts[:] = original
    window.close()


def test_desktop_widths_survive_compact_layout_and_restart(catalog, qapp):
    window = MainWindow(catalog)
    window.resize(1200, 640)
    window.show()
    qapp.processEvents()
    window.splitter.moveSplitter(610, 2)
    desktop_sizes = window.splitter.sizes()
    assert desktop_sizes[1] > 380

    for width in (860, 700, 860, 1200):
        window.resize(width, 640)
        qapp.processEvents()
    assert window.splitter.sizes() == desktop_sizes
    window.resize(700, 640)
    qapp.processEvents()
    window.close()

    reopened = MainWindow(catalog)
    reopened.resize(700, 640)
    reopened.show()
    qapp.processEvents()
    assert not reopened.sidebar.isVisible()
    reopened.resize(1200, 640)
    qapp.processEvents()
    assert reopened.splitter.sizes() == desktop_sizes
    reopened.close()
