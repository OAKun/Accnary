# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 19:01
# @Modified  : 2026-10-25 20:25
# @Python    : 3.14.9
# @Description: Detail panel rendering and layout regression tests.
"""Detail panel rendering tests (offscreen)."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QToolButton

from app.models import LicenseInfo, LicenseMode
from app.ui.detail_panel import DetailPanel
from app.ui.widgets import CopyRow, SecretRow


def _walk(widget) -> str:
    """All QLabel texts in the panel, joined."""
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


def test_show_account_renders_sections(catalog, qapp):
    account = catalog.catalog.all_accounts()[0]
    service = catalog.catalog.services[0]
    panel = DetailPanel(catalog)
    panel.show_account(service, account)

    text = _walk(panel)
    assert "UI云盘" in text
    assert "主账号" in text          # alias badge
    assert "ui-user" in text         # username
    assert "微信授权登录 · 微信主号" in text  # login method + identity label
    assert "登录手机号" in text       # binding role
    assert "订阅" in text            # license mode
    assert "UI-KEY-1" not in text    # license key stays masked (••••)


def test_password_masked_until_revealed(catalog, qapp):
    account = catalog.catalog.all_accounts()[0]
    panel = DetailPanel(catalog)
    panel.show_account(catalog.catalog.services[0], account)

    secrets = panel._content.findChildren(SecretRow)
    assert secrets, "password/license secret rows must exist"
    password_row = next(r for r in secrets if r._value == "ui-pass-9")
    assert password_row.value_label.text() == "••••••••"
    password_row._toggle()
    assert password_row.value_label.text() == "ui-pass-9"
    password_row._toggle()
    assert password_row.value_label.text() == "••••••••"


def test_narrow_details_give_values_more_space(catalog, qapp):
    service = catalog.catalog.services[0]
    account = service.accounts[0]
    service.name = "Example" * 30
    account.primary_url = "https://example.invalid/" + "segment/" * 20
    panel = DetailPanel(catalog)
    panel.resize(320, 600)
    panel.show_account(service, account)
    panel.show()
    qapp.processEvents()
    row = next(
        row for row in panel.findChildren(CopyRow)
        if row.value_label.text() == account.primary_url
    )
    key = next(label for label in row.findChildren(QLabel) if label.text() == "主网址")
    assert row.value_label.y() >= key.geometry().bottom()
    assert row.value_label.width() >= 160
    assert row.copy_btn.geometry().right() < row.width()
    assert panel._scroll.horizontalScrollBar().maximum() == 0

    panel.resize(700, 600)
    qapp.processEvents()
    assert row.value_label.x() > key.geometry().right()
    assert row.value_label.text() == account.primary_url
    panel.close()


def test_show_empty_hint(catalog, qapp):
    panel = DetailPanel(catalog)
    panel.show_empty("测试提示")
    assert "测试提示" in _walk(panel)


def test_edit_action_moves_below_title_in_narrow_detail(catalog, qapp):
    service = catalog.catalog.services[0]
    panel = DetailPanel(catalog)
    panel.resize(320, 600)
    panel.show_account(service, service.accounts[0])
    panel.show()
    qapp.processEvents()
    edit = panel.findChild(QToolButton, "editAccount")
    title = next(label for label in panel.findChildren(QLabel) if label.text() == service.name)
    assert edit.text() == "编辑"
    assert edit.mapTo(panel, edit.rect().topLeft()).y() > title.mapTo(panel, title.rect().bottomLeft()).y()

    panel.resize(700, 600)
    qapp.processEvents()
    assert edit.mapTo(panel, edit.rect().topLeft()).x() > title.mapTo(panel, title.rect().topRight()).x()
    panel.close()


def test_primary_url_is_grouped_with_credentials_without_duplicate(catalog, qapp):
    service = catalog.catalog.services[0]
    account = service.accounts[0]
    alternate = "https://example.invalid/alternate"
    service.urls = [account.primary_url, alternate]
    service.login_urls = [alternate]
    panel = DetailPanel(catalog)
    panel.show_account(service, account)
    rows = panel.findChildren(CopyRow)
    primary = [row for row in rows if row.value_label.text() == account.primary_url]
    assert len(primary) == 1
    assert primary[0].parentWidget().objectName() == "credentials"
    assert sum(row.value_label.text() == alternate for row in rows) == 1
    assert "其他登录网址" in _walk(panel)


def test_empty_detail_is_centered_in_scroll_view(catalog, qapp):
    panel = DetailPanel(catalog)
    panel.resize(704, 700)
    panel.show_empty("没有匹配的账户")
    panel.show()
    qapp.processEvents()

    heading = next(label for label in panel.findChildren(QLabel) if label.text() == "账户详情")
    hint = next(label for label in panel.findChildren(QLabel) if label.text() == "没有匹配的账户")
    group_center = (heading.geometry().top() + hint.geometry().bottom()) / 2
    view_center = panel._content.height() / 2
    assert abs(group_center - view_center) <= 24
    panel.close()


def test_license_hidden_when_mode_none(catalog, qapp):
    account = catalog.catalog.all_accounts()[0]
    service = catalog.catalog.services[0]
    account.license = LicenseInfo(mode=LicenseMode.NONE)
    panel = DetailPanel(catalog)
    panel.show_account(service, account)
    assert "付费授权" not in _walk(panel)
