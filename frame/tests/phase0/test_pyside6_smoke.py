"""Phase 0: PySide6 smoke test - the Qt stack boots headlessly.

No UI design here; this only proves QApplication + widgets + rendering work
on this Python version before Phase 2 commits to the stack.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets", reason="PySide6-Essentials not installed")

import PySide6  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_qt_versions(qapp):
    print(f"PySide6 {PySide6.__version__} / Qt {QtCore.qVersion()}")
    assert QtCore.qVersion()


def test_widget_text_roundtrip(qapp):
    label = QtWidgets.QLabel()
    label.setText("Accnary Phase 0")
    assert label.text() == "Accnary Phase 0"


def test_offscreen_rendering(qapp):
    label = QtWidgets.QLabel()
    label.setText("Accnary render check")
    label.resize(320, 80)
    pixmap = label.grab()
    assert not pixmap.isNull()


def test_main_window_setup(qapp):
    win = QtWidgets.QMainWindow()
    win.setWindowTitle("Accnary")
    win.resize(1200, 800)
    assert win.windowTitle() == "Accnary"
    assert win.size().width() == 1200


def test_high_dpi_attributes(qapp):
    # High-DPI scaling is on by default in Qt 6; verify the policy is queryable.
    assert qapp.devicePixelRatio() > 0
