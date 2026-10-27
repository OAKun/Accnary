# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 19:01
# @Modified  : 2026-10-25 20:25
# @Python    : 3.14.9
# @Description: Detail panel rendering and layout regression tests.
"""Detail panel rendering tests (offscreen)."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from app.models import LicenseInfo, LicenseMode
from app.ui.detail_panel import DetailPanel


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
    from app.ui.widgets import SecretRow

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


def test_show_empty_hint(catalog, qapp):
    panel = DetailPanel(catalog)
    panel.show_empty("测试提示")
    assert "测试提示" in _walk(panel)


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
