# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-25 11:23
# @Modified  : 2026-10-26 01:00
# @Python    : 3.14.9
# @Description: Explicit workspace palette expectations and conditional clipboard behavior.
"""Theme + clipboard behavior tests (offscreen)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app.security.clipboard import clear_if_unchanged, copy_with_auto_clear
from app.ui import theme


def test_theme_light_and_dark_apply(qapp):
    theme.apply_theme(qapp, "light")
    light = qapp.styleSheet()
    assert light and "#f5f7fa" in light
    assert "#ebf2ff" in light and "#2f68d5" in light
    assert "@" not in light

    theme.apply_theme(qapp, "dark")
    dark = qapp.styleSheet()
    assert "#181f2b" in dark and dark != light

    theme.apply_theme(qapp, "light")  # restore for other tests
    assert "#f5f7fa" in qapp.styleSheet()


def test_theme_toggle_flips(qapp):
    before = theme.current_theme()
    after = theme.toggle_theme(qapp)
    assert after != before
    theme.apply_theme(qapp, "light")


def test_clipboard_copy_and_conditional_clear(qapp):
    clipboard = QApplication.clipboard()
    copy_with_auto_clear("secret-token-1", clear_after_ms=50)
    assert clipboard.text() == "secret-token-1"

    # user copied something else in the meantime -> our value must NOT clear it
    clipboard.setText("user-copied-this")
    assert clear_if_unchanged("secret-token-1") is False
    assert clipboard.text() == "user-copied-this"

    # still ours -> cleared
    clipboard.setText("secret-token-2")
    assert clear_if_unchanged("secret-token-2") is True
    assert clipboard.text() == ""
