# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 21:12
# @Modified  : 2026-10-26 21:16
# @Python    : 3.14.9
# @Description: Accnary app / ui / widgets
"""Reusable row widgets for the detail panel and editor."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.security.clipboard import copy_with_auto_clear
from app.security.password_generator import (
    GeneratorPolicy,
    PasswordGeneratorError,
    generate_password,
)
from app.ui import icons, theme

MASK = "••••••••"


def _muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("muted", True)
    return label


class SectionHeader(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setProperty("section", True)


class Card(QFrame):
    """A rounded panel container."""

    def __init__(self):
        super().__init__()
        self.setProperty("card", True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)

    def add_row(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


class CopyRow(QWidget):
    """Label + (copyable) value + 复制 button, for non-secret values."""

    def __init__(self, label: str, value: str = "", parent=None, on_copied: Callable[[], None] | None = None):
        super().__init__(parent)
        self._on_copied = on_copied
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        key = _muted_label(label)
        key.setFixedWidth(64)
        self.value_label = QLabel(value)
        self.value_label.setTextFormat(Qt.TextFormat.PlainText)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value_label.setWordWrap(True)
        self.value_label.setMinimumWidth(0)
        self.value_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(36)
        self.copy_btn = QToolButton()
        self.copy_btn.setObjectName("copyValueButton")
        self.copy_btn.setIcon(icons.line_icon("copy", theme.PALETTES[theme.current_theme()]["muted"]))
        self.copy_btn.setToolTip(f"复制{label}")
        self.copy_btn.setAccessibleName(f"复制{label}")
        self.copy_btn.setAutoRaise(True)
        self.copy_btn.setFixedSize(32, 32)
        self.copy_btn.clicked.connect(self._copy)
        layout.addWidget(key)
        layout.addWidget(self.value_label, 1)
        layout.addWidget(self.copy_btn)
        self.copy_btn.setVisible(bool(value))
        self._value = value

    def set_value(self, value: str) -> None:
        self._value = value
        self.value_label.setText(value)
        self.copy_btn.setVisible(bool(value))

    def _copy(self) -> None:
        copy_with_auto_clear(self._value)
        if self._on_copied is not None:
            self._on_copied()


class SecretRow(QWidget):
    """Label + masked secret + 显示/隐藏 + 复制."""

    def __init__(self, label: str, value: str = "", parent=None, on_copied: Callable[[], None] | None = None):
        super().__init__(parent)
        self._on_copied = on_copied
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        key = _muted_label(label)
        key.setFixedWidth(48)
        self.value_label = QLabel(MASK if value else "未填写")
        self.value_label.setTextFormat(Qt.TextFormat.PlainText)
        self.value_label.setWordWrap(True)
        self.value_label.setMinimumWidth(0)
        self.value_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(36)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._label = label
        self.toggle_btn = QToolButton()
        self.toggle_btn.setObjectName("toggleSecretButton")
        self.toggle_btn.setIcon(icons.line_icon("eye", theme.PALETTES[theme.current_theme()]["muted"]))
        self.toggle_btn.setToolTip(f"显示{label}")
        self.toggle_btn.setAccessibleName(f"显示{label}")
        self.toggle_btn.setAutoRaise(True)
        self.toggle_btn.setFixedSize(32, 32)
        self.toggle_btn.clicked.connect(self._toggle)
        self.copy_btn = QToolButton()
        self.copy_btn.setObjectName("copySecretButton")
        self.copy_btn.setIcon(icons.line_icon("copy", theme.PALETTES[theme.current_theme()]["muted"]))
        copy_name = "复制密码" if label == "密码" else f"复制{label}"
        self.copy_btn.setToolTip(copy_name)
        self.copy_btn.setAccessibleName(copy_name)
        self.copy_btn.setAutoRaise(True)
        self.copy_btn.setFixedSize(32, 32)
        self.copy_btn.clicked.connect(self._copy)
        layout.addWidget(key)
        layout.addWidget(self.value_label, 1)
        layout.addWidget(self.toggle_btn)
        layout.addWidget(self.copy_btn)
        self.set_value(value)

    def set_value(self, value: str) -> None:
        self._value = value or ""
        self._revealed = False
        self.value_label.setText(MASK if self._value else "未填写")
        self.toggle_btn.setVisible(bool(self._value))
        self.copy_btn.setVisible(bool(self._value))
        self.toggle_btn.setIcon(icons.line_icon("eye", theme.PALETTES[theme.current_theme()]["muted"]))
        self.toggle_btn.setToolTip(f"显示{self._label}")
        self.toggle_btn.setAccessibleName(f"显示{self._label}")

    def _toggle(self) -> None:
        self._revealed = not self._revealed
        self.value_label.setText(self._value if self._revealed else MASK)
        action = "隐藏" if self._revealed else "显示"
        icon_name = "eye_off" if self._revealed else "eye"
        self.toggle_btn.setIcon(icons.line_icon(icon_name, theme.PALETTES[theme.current_theme()]["muted"]))
        self.toggle_btn.setToolTip(f"{action}{self._label}")
        self.toggle_btn.setAccessibleName(f"{action}{self._label}")

    def _copy(self) -> None:
        copy_with_auto_clear(self._value)
        if self._on_copied is not None:
            self._on_copied()

    def clear_sensitive(self) -> None:
        self._on_copied = None
        self.set_value("")


class PasswordInput(QWidget):
    """Editor-side password field: hidden input + 显示 toggle + 生成… popover."""

    def __init__(self, with_generator: bool = True, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.toggle_btn = QToolButton()
        self.toggle_btn.setText("显示")
        self.toggle_btn.setAccessibleName("显示密码")
        self.toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.toggle_btn)
        if with_generator:
            self.generate_btn = QToolButton()
            self.generate_btn.setText("生成…")
            self.generate_btn.setAccessibleName("生成密码")
            self.generate_btn.clicked.connect(self._open_generator)
            layout.addWidget(self.generate_btn)

    def text(self) -> str:
        return self.edit.text()

    def set_text(self, value: str) -> None:
        self.edit.setText(value or "")

    def _toggle(self) -> None:
        hidden = self.edit.echoMode() == QLineEdit.EchoMode.Password
        self.edit.setEchoMode(
            QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password
        )
        self.toggle_btn.setText("隐藏" if hidden else "显示")
        self.toggle_btn.setAccessibleName("隐藏密码" if hidden else "显示密码")

    def _open_generator(self) -> None:
        from PySide6.QtCore import QPoint

        popup = GeneratorPopup(self)
        pos = self.generate_btn.mapToGlobal(QPoint(0, self.generate_btn.height()))
        popup.move(pos)
        popup.exec()
        if popup.generated_password:
            self.edit.setText(popup.generated_password)
            self.edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_btn.setText("显示")
            self.toggle_btn.setAccessibleName("显示密码")
        popup.preview_edit.clear()
        popup.generated_password = ""
        popup.deleteLater()


class GeneratorPopup(QDialog):
    """Password generator policy panel (spec section 6: 可配置策略)."""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.generated_password: str = ""
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("长度"))
        self.length_spin = QSpinBox()
        self.length_spin.setRange(8, 128)
        self.length_spin.setValue(20)
        row.addWidget(self.length_spin)
        row.addStretch(1)
        layout.addLayout(row)

        self.upper_check = QCheckBox("大写字母 (A-Z)")
        self.lower_check = QCheckBox("小写字母 (a-z)")
        self.digits_check = QCheckBox("数字 (0-9)")
        self.special_check = QCheckBox("符号 (!@#$…)")
        for check, state in (
            (self.upper_check, True),
            (self.lower_check, True),
            (self.digits_check, True),
            (self.special_check, True),
        ):
            check.setChecked(state)
            layout.addWidget(check)
        self.no_similar_check = QCheckBox("排除易混淆字符 (Il1O0o)")
        self.no_similar_check.setChecked(True)
        layout.addWidget(self.no_similar_check)

        exclude_row = QHBoxLayout()
        exclude_row.addWidget(QLabel("排除字符"))
        self.exclude_edit = QLineEdit()
        self.exclude_edit.setPlaceholderText("如: 0O")
        exclude_row.addWidget(self.exclude_edit, 1)
        layout.addLayout(exclude_row)

        self.preview_edit = QLineEdit()
        self.preview_edit.setReadOnly(True)
        layout.addWidget(self.preview_edit)

        buttons = QHBoxLayout()
        regen_btn = QPushButton("重新生成")
        regen_btn.clicked.connect(self._regenerate)
        use_btn = QPushButton("使用")
        use_btn.setProperty("variant", "primary")
        use_btn.clicked.connect(self._use)
        cancel_btn = QPushButton("关闭")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(regen_btn)
        buttons.addStretch(1)
        buttons.addWidget(use_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        self._regenerate()

    def _policy(self) -> GeneratorPolicy:
        return GeneratorPolicy(
            length=self.length_spin.value(),
            upper=self.upper_check.isChecked(),
            lower=self.lower_check.isChecked(),
            digits=self.digits_check.isChecked(),
            special=self.special_check.isChecked(),
            exclude_similar=self.no_similar_check.isChecked(),
            exclude=self.exclude_edit.text().strip(),
        )

    def _regenerate(self) -> None:
        try:
            self.preview_edit.setText(generate_password(self._policy()))
        except PasswordGeneratorError as exc:
            self.preview_edit.clear()
            self.preview_edit.setPlaceholderText(f"无法生成：{exc}")

    def _use(self) -> None:
        self.generated_password = self.preview_edit.text()
        if self.generated_password:
            self.accept()
