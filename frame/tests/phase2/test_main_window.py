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

from .conftest import TEST_PASSWORD


def _row_texts(window: MainWindow) -> list[str]:
    return [window.account_list.item(i).text() for i in range(window.account_list.count())]


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


@pytest.mark.parametrize("window_width", [535, 860])
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
