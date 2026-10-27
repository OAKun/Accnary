# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-25 11:27
# @Modified  : 2026-10-27 11:15
# @Python    : 3.14.9
# @Description: Compact local appearance and existing idle-lock preferences.
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.ui import theme
from app.ui.settings import app_settings
from app.version import APP_VERSION


class SettingsDialog(QDialog):
    theme_changed = Signal(str)
    change_master_password_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setObjectName("settingsDialog")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        title = QLabel("偏好设置")
        title.setProperty("pageTitle", True)
        layout.addWidget(title)
        form = QFormLayout()
        form.setSpacing(16)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(theme.current_theme()))
        self.theme_combo.currentIndexChanged.connect(lambda _i: self.theme_changed.emit(self.theme_combo.currentData()))
        form.addRow("外观", self.theme_combo)
        self.idle_combo = QComboBox()
        for label, minutes in (("禁用", 0), ("5 分钟", 5), ("10 分钟", 10), ("15 分钟", 15), ("30 分钟", 30)):
            self.idle_combo.addItem(label, minutes)
        current = int(app_settings().value("idle_lock_minutes", 10))
        self.idle_combo.setCurrentIndex(self.idle_combo.findData(current))
        self.idle_combo.currentIndexChanged.connect(
            lambda _i: app_settings().setValue("idle_lock_minutes", self.idle_combo.currentData()))
        form.addRow("空闲自动锁定", self.idle_combo)
        self.auto_update_checkbox = QCheckBox("启动时自动检查更新（仅提示，不会自动下载）")
        self.auto_update_checkbox.setChecked(
            app_settings().value("update/auto_check", True, type=bool)
        )
        self.auto_update_checkbox.toggled.connect(
            lambda enabled: app_settings().setValue("update/auto_check", enabled)
        )
        form.addRow("软件更新", self.auto_update_checkbox)
        layout.addLayout(form)
        security_title = QLabel("安全")
        security_title.setProperty("section", True)
        layout.addWidget(security_title)
        security_row = QHBoxLayout()
        security_hint = QLabel("修改主密码；忘记后无法通过 KDBX 重置。")
        security_hint.setProperty("muted", True)
        security_hint.setWordWrap(True)
        security_row.addWidget(security_hint, 1)
        change_password = QPushButton("修改主密码…")
        change_password.clicked.connect(self.change_master_password_requested.emit)
        security_row.addWidget(change_password)
        layout.addLayout(security_row)
        backup_hint = QLabel("已有加密备份仍需使用生成时的主密码。")
        backup_hint.setProperty("muted", True)
        backup_hint.setWordWrap(True)
        layout.addWidget(backup_hint)
        about = QLabel(
            f"Accnary {APP_VERSION} 首发版\n"
            "本地 KDBX 加密存储 · 按需启动 · 关闭即退出\n"
            "未经独立第三方安全审计。"
        )
        about.setWordWrap(True)
        about.setProperty("muted", True)
        layout.addWidget(about)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("完成")
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)
