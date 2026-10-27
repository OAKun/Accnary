# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 18:52
# @Modified  : 2026-10-24 23:40
# @Python    : 3.14.9
# @Description: Accnary app / security / clipboard
"""Clipboard copy with timed conditional clear (spec section 6).

After copying a secret, a timer clears the clipboard ONLY if the user has
not copied something else in the meantime. Known residual risks (documented,
cannot be eliminated from an app): Windows 剪贴板历史 (Win+V) and other
clipboard managers may have already captured the value.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

DEFAULT_CLEAR_AFTER_MS = 30_000


class _ClipboardGuard(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.expected: str | None = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.clear)
        app.clipboard().dataChanged.connect(self._changed)
        app.aboutToQuit.connect(self.clear)

    def _changed(self):
        # Any later clipboard write relinquishes ownership, even if it has
        # the same text. This also drops the retained secret immediately.
        self.expected = None
        self.timer.stop()

    def copy(self, text, milliseconds):
        self.timer.stop()
        QApplication.clipboard().setText(text)
        self.expected = text
        self.timer.start(milliseconds)

    def clear(self):
        expected = self.expected
        self.expected = None
        self.timer.stop()
        if expected is not None:
            clear_if_unchanged(expected)


def _guard():
    app = QApplication.instance()
    if not hasattr(app, "_accnary_clipboard_guard"):
        app._accnary_clipboard_guard = _ClipboardGuard(app)
    return app._accnary_clipboard_guard


def copy_with_auto_clear(text: str, clear_after_ms: int = DEFAULT_CLEAR_AFTER_MS) -> None:
    """Copy ``text`` and schedule a conditional clear."""
    _guard().copy(text, clear_after_ms)


def clear_owned_clipboard() -> None:
    """Stop our timer and clear only the clipboard value we still own."""
    _guard().clear()


def clear_if_unchanged(expected: str) -> bool:
    """Clear the clipboard only when it still holds ``expected``.

    Returns True when the clipboard was cleared.
    """
    clipboard = QApplication.clipboard()
    if clipboard.text() == expected:
        clipboard.clear()
        return True
    return False
