# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-25 17:58
# @Modified  : 2026-10-25 23:45
# @Python    : 3.14.9
# @Description: Accnary dialog for changing the current KDBX master password.
"""Change the unlocked vault's master password without exposing it in logs."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.errors import AccnaryError, BadCredentialsError
from app.ui.storage_task import run_storage_task


class MasterPasswordDialog(QDialog):
    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self._catalog = catalog
        self.setWindowTitle("修改主密码")
        self.setObjectName("masterPasswordDialog")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        hint = QLabel(
            "输入当前主密码并设置新密码。新密码至少 8 个字符。\n"
            "主密码无法找回；已有加密备份仍需使用旧主密码。"
        )
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)
        self.current_edit = self._password_field("当前主密码")
        self.new_edit = self._password_field("新主密码")
        self.confirm_edit = self._password_field("再次输入新主密码")
        form.addRow("当前主密码", self.current_edit)
        form.addRow("新主密码", self.new_edit)
        form.addRow("确认新主密码", self.confirm_edit)
        layout.addLayout(form)

        self.show_passwords = QCheckBox("显示密码")
        self.show_passwords.toggled.connect(self._set_password_visibility)
        layout.addWidget(self.show_passwords)

        self.error_label = QLabel()
        self.error_label.setProperty("error", True)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("修改")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("variant", "primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._change)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.current_edit.setFocus()

    @staticmethod
    def _password_field(placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setPlaceholderText(placeholder)
        field.setClearButtonEnabled(True)
        return field

    def _set_password_visibility(self, visible: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        for field in (self.current_edit, self.new_edit, self.confirm_edit):
            field.setEchoMode(mode)

    def _change(self) -> None:
        current = self.current_edit.text()
        new = self.new_edit.text()
        confirm = self.confirm_edit.text()

        if not current:
            self._show_error("请输入当前主密码。")
            self.current_edit.setFocus()
            return
        if len(new) < 8:
            self._show_error("新主密码至少需要 8 个字符。")
            self.new_edit.setFocus()
            return
        if new != confirm:
            self._show_error("两次输入的新主密码不一致。")
            self.confirm_edit.selectAll()
            self.confirm_edit.setFocus()
            return
        if new == current:
            self._show_error("新主密码需要与当前主密码不同。")
            self.new_edit.selectAll()
            self.new_edit.setFocus()
            return

        try:
            run_storage_task(
                self,
                "正在修改主密码并安全保存…",
                lambda: self._catalog.change_master_password(current, new),
            )
        except BadCredentialsError:
            self._show_error("当前主密码不正确。")
            self.current_edit.selectAll()
            self.current_edit.setFocus()
            return
        except AccnaryError as exc:
            self._show_error(f"修改失败：{exc}")
            return
        except Exception as exc:
            self._show_error(f"修改失败（{type(exc).__name__}）。原主密码仍可用于解锁。")
            return
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()

    def done(self, result: int) -> None:
        for field in (self.current_edit, self.new_edit, self.confirm_edit):
            field.clear()
        super().done(result)
