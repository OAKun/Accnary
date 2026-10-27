# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 18:53
# @Modified  : 2026-10-26 17:46
# @Python    : 3.14.9
# @Description: Accnary app / ui / theme
"""Theme system: light-first modern QSS with a dark variant.

Palettes are plain dicts; the stylesheet is a plain template using
@TOKEN@ placeholders (avoids brace-escaping pain with QSS).
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#ffffff",
        "sidebar": "#f5f7fa",
        "panel": "#ffffff",
        "panel2": "#f7f9fc",
        "border": "#e7ecf3",
        "text": "#202938",
        "muted": "#667386",
        "accent": "#2f68d5",
        "accent_bg": "#2f68d5",
        "accent_hover": "#2456b8",
        "accent_text": "#ffffff",
        "danger": "#c83232",
        "hover": "#f2f6fb",
        "selected": "#ebf2ff",
        "input_bg": "#ffffff",
    },
    "dark": {
        "bg": "#181f2b",
        "sidebar": "#19222f",
        "panel": "#1e2735",
        "panel2": "#242f40",
        "border": "#303c50",
        "text": "#e6edf8",
        "muted": "#a9b6ca",
        "accent": "#7096e8",
        "accent_bg": "#326bd8",
        "accent_hover": "#2f65c7",
        "accent_text": "#ffffff",
        "danger": "#e06c6c",
        "hover": "#263348",
        "selected": "#2a3d5b",
        "input_bg": "#1b1f25",
    },
}

_current: str = "light"

# Logical pixels: Qt applies the display's device-pixel ratio once.
TYPE = {"small": 12, "body": 14, "pane": 16, "brand": 19, "title": 21}
SPACE = (4, 8, 16, 24, 32)
CONTROL_HEIGHT = 36
RADIUS = 6


def current_theme() -> str:
    return _current


_QSS_TEMPLATE = """
* { font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif; font-size: 13px; }
QWidget { background: @BG@; color: @TEXT@; }
QMainWindow, QDialog { background: @BG@; }
QWidget#workspaceRoot { background: @PANEL@; }
QWidget#lockPage { background: @SIDEBAR@; }
QFrame#lockCard { background: @PANEL@; border: 1px solid @BORDER@; border-radius: 12px; }
QWidget#appHeader { background: @PANEL@; border-bottom: 1px solid @BORDER@; }
QWidget#headerSeparator { background: @BORDER@; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background: @INPUT_BG@; border: 1px solid @BORDER@; border-radius: 6px;
    padding: 7px 10px; min-height: 22px; selection-background-color: @ACCENT_BG@; color: @TEXT@;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
    border: 1px solid @ACCENT@;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: @PANEL@; border: 1px solid @BORDER@;
    selection-background-color: @SELECTED@; selection-color: @TEXT@;
}

QPushButton {
    background: @PANEL@; border: 1px solid @BORDER@; border-radius: 6px;
    padding: 6px 16px; min-height: 22px; color: @TEXT@;
}
QPushButton:hover { background: @HOVER@; border-color: @ACCENT@; }
QPushButton:pressed { background: @SELECTED@; }
QPushButton:disabled { color: @MUTED@; border-color: @BORDER@; }
QPushButton[variant="primary"] {
    background: @ACCENT_BG@; border: 1px solid @ACCENT_BG@; color: @ACCENT_TEXT@; font-weight: 600;
}
QPushButton[variant="primary"]:hover { background: @ACCENT_HOVER@; border-color: @ACCENT_HOVER@; }
QPushButton[variant="primary"]:disabled {
    background: @HOVER@; border-color: @BORDER@; color: @MUTED@;
}
QPushButton[variant="danger"] { color: @DANGER@; border-color: @DANGER@; background: transparent; }
QPushButton[variant="danger"]:hover { background: @PANEL@; }
QPushButton[variant="ghost"] { border: 1px solid transparent; background: transparent; color: @ACCENT@; padding: 3px 8px; }
QPushButton[variant="ghost"]:hover { background: @HOVER@; }

QListWidget, QTreeWidget, QListView {
    background: @PANEL@; border: 1px solid @BORDER@; border-radius: 10px;
    outline: none; padding: 7px;
}
QListWidget::item { border-radius: 6px; margin: 1px 2px; color: @TEXT@; }
QListWidget::item:selected { background: @SELECTED@; color: @TEXT@; }
QListWidget::item:hover { background: @HOVER@; }

QLabel { background: transparent; }
QLabel[muted="true"] { color: @MUTED@; font-size: 12px; }
QLabel[error="true"] { color: @DANGER@; }
QLabel[warning="true"] { color: @DANGER@; }
QLabel[section="true"] {
    color: @MUTED@; font-size: 12px; font-weight: 600;
}
QLabel[title="true"] { font-size: 21px; font-weight: 600; }
QLabel[badge="true"] {
    background: @HOVER@; color: @ACCENT@; border-radius: 8px; padding: 1px 8px; font-size: 10pt;
}

QFrame[card="true"] {
    background: @PANEL@; border: 1px solid @BORDER@; border-radius: 8px;
}
QFrame[divider="true"] { background: @BORDER@; max-height: 1px; border: none; }

QToolButton { background: transparent; border: none; border-radius: 6px; padding: 7px 10px; color: @TEXT@; }
QToolButton:hover { background: @HOVER@; }
QToolButton#lockButton { padding: 7px 12px; color: @MUTED@; }
QToolButton#lockButton:hover { background: @HOVER@; color: @TEXT@; }
QToolButton#moreMenuButton { padding: 7px; min-width: 22px; }
QToolButton#navigationToggle, QToolButton#backToList { padding: 7px 10px; }
QToolButton::menu-indicator { image: none; width: 0; }

QMenu { background: @PANEL@; border: 1px solid @BORDER@; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: @SELECTED@; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @BORDER@; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: @MUTED@; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: @BORDER@; border-radius: 5px; min-width: 30px; }

QSplitter::handle { background: @BORDER@; width: 1px; }
QSplitter::handle:hover { background: @ACCENT@; }

QWidget#sidebar { background: @SIDEBAR@; }
QListWidget#navigation { background: transparent; border: none; border-radius: 0; padding: 0; }
QListWidget#navigation QWidget { background: transparent; }
QListWidget#navigation::item { min-height: 24px; padding: 8px; margin: 2px 0; border-radius: 5px; }
QListWidget#navigation::item:selected { background: @SELECTED@; color: @ACCENT@; font-weight: 600; }
QListWidget#navigation::item:disabled { color: @MUTED@; background: transparent; font-size: 11px; }
QWidget#listPane, QWidget#listHeader, QLabel#listEmpty { background: @PANEL@; }
QWidget#listHeader { border-bottom: 1px solid @BORDER@; }
QListWidget#accountList { background: @PANEL@; border: none; border-radius: 0; padding: 4px 0; }
QListWidget#accountList::item { padding: 0; margin: 0; border: none; }
QLabel#listEmpty { color: @MUTED@; padding: 24px; }
QLabel#localHint { color: @MUTED@; font-size: 11px; padding: 12px 4px 0 4px; }
QWidget#detailPane, QWidget#detailShell { background: @PANEL@; }
QWidget#detailPane QWidget, QWidget#detailContent { background: transparent; }
QWidget#detailPane QWidget#detailShell, QWidget#detailPane QWidget#detailContent,
QWidget#detailPane QScrollArea { background: @PANEL@; }
QWidget#detailPane QFrame[card="true"] { background: transparent; border: none; border-bottom: 1px solid @BORDER@; border-radius: 0; padding-bottom: 8px; }
QWidget#detailPane QFrame#credentials { background: @PANEL2@; border: none; border-radius: 8px; }
QWidget#detailPane QPushButton { background: @PANEL@; }
QWidget#detailPane QPushButton[variant="ghost"] { background: transparent; }
QWidget#detailPane QPushButton:hover { background: @HOVER@; }
QWidget#detailPane QToolButton { background: transparent; border: none; border-radius: 6px; padding: 4px; }
QWidget#detailPane QToolButton:hover { background: @HOVER@; }
QPushButton::menu-indicator { image: none; width: 0; }
QWidget#accountRow { background: transparent; }
QLabel[avatar="true"] { background: @HOVER@; color: @ACCENT@; border-radius: 10px; font-size: 15pt; font-weight: 600; }
QLabel[rowTitle="true"] { font-size: 11pt; font-weight: 600; }
QLabel[brand="true"] { font-size: 19px; font-weight: 600; padding-right: 16px; }
QLabel#vaultLabel { color: @MUTED@; padding-left: 4px; font-size: 12px; }
QLabel[paneTitle="true"] { font-size: 16px; font-weight: 600; }
QLabel[pageTitle="true"] { font-size: 22px; font-weight: 600; }
QLineEdit#globalSearch { background: @PANEL2@; min-height: 22px; padding: 7px 8px; border-radius: 6px; }
QComboBox#accountSort { border: none; background: transparent; padding: 2px 4px; color: @MUTED@; font-size: 12px; min-height: 20px; }
QToolButton[variant="primary"] { background: @ACCENT_BG@; color: @ACCENT_TEXT@; padding: 8px 14px; font-weight: 600; }
QToolButton[variant="primary"]:hover { background: @ACCENT_HOVER@; }
QToolButton[variant="danger"] { color: @DANGER@; }
QToolButton#moreOptions { color: @ACCENT@; background: @HOVER@; padding: 10px; text-align: left; }
QDialog#accountEditor { background: @PANEL@; }
QDialog#accountEditor QScrollArea, QDialog#accountEditor QWidget#editorBody { background: @PANEL@; border: none; }
QWidget#dialogFooter { background: @PANEL2@; border-top: 1px solid @BORDER@; }

QTabWidget::pane { border: none; background: @PANEL@; }
QTabBar::tab { color: @MUTED@; background: transparent; padding: 12px 14px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: @ACCENT@; border-bottom: 2px solid @ACCENT@; font-weight: 600; }
QTabBar::tab:hover { background: @HOVER@; }
QDialog#accountEditor QTabWidget QWidget { background: @PANEL@; }
QToolTip { background: @PANEL@; color: @TEXT@; border: 1px solid @BORDER@; padding: 4px; }
QMessageBox { background: @PANEL@; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid @BORDER@; border-radius: 4px; background: @INPUT_BG@; }
QCheckBox::indicator:checked { background: @ACCENT@; border-color: @ACCENT@; }
"""


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply the named theme ('light' | 'dark') to the application."""
    global _current
    palette = PALETTES.get(theme, PALETTES["light"])
    qss = _QSS_TEMPLATE
    for token, value in palette.items():
        qss = qss.replace(f"@{token.upper()}@", value)
    app.setStyleSheet(qss)
    _current = theme


def toggle_theme(app: QApplication) -> str:
    new_theme = "dark" if _current == "light" else "light"
    apply_theme(app, new_theme)
    return new_theme
