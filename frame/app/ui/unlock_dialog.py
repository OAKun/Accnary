# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 20:14
# @Modified  : 2026-10-26 22:03
# @Python    : 3.14.9
# @Description: Accnary app / ui / unlock_dialog
"""Master-password unlock dialog with vault picker and create flow.

Recent vault PATHS are remembered via QSettings (paths only - never any
credential material). Tests can monkeypatch load_recent_paths /
remember_recent_path to keep settings isolated.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.errors import AccnaryError, BadCredentialsError, VaultError, VaultFormatError
from app.services import CatalogService
from app.ui.settings import app_settings
from app.ui.storage_task import run_storage_task

_RECENT_KEY = "recent_vaults"
_MAX_RECENT = 5
_ENV_VAR_PATTERN = re.compile(
    r"%([^%]+)%|\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)"
)


def load_recent_paths() -> list[str]:
    settings = app_settings()
    raw = settings.value(_RECENT_KEY, [])
    if isinstance(raw, str):
        raw = [raw]
    paths = []
    for item in raw or []:
        if not isinstance(item, str):
            continue
        try:
            path = resolve_vault_path(item)
        except ValueError:
            continue
        if path.is_file():
            paths.append(str(path))
    return paths


def remember_recent_path(path: str) -> None:
    settings = app_settings()
    items = [p for p in settings.value(_RECENT_KEY, []) or [] if isinstance(p, str)]
    items = [path] + [p for p in items if p != path]
    settings.setValue(_RECENT_KEY, items[:_MAX_RECENT])


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def default_vault_path() -> str:
    return "./data/Accnary.kdbx"


def resolve_vault_path(path: str | Path) -> Path:
    path_text = str(path).strip().strip('"')
    env_names = {
        match.group(1) or match.group(2) or match.group(3)
        for match in _ENV_VAR_PATTERN.finditer(path_text)
    }
    missing = sorted(name for name in env_names if not os.environ.get(name))
    if missing:
        variables = ", ".join(f"%{name}%" for name in missing)
        raise ValueError(f"路径中的环境变量未设置：{variables}。请检查 Windows 环境变量。")

    candidate = Path(os.path.expandvars(os.path.expanduser(path_text)))
    if not candidate.is_absolute():
        candidate = application_root() / candidate
    return candidate.resolve()


class UnlockDialog(QDialog):
    """Unlock an existing vault or create a new one."""

    def __init__(self, parent=None, vault_path: str | None = None):
        super().__init__(parent)
        self.catalog: CatalogService | None = None
        self.setWindowTitle("Accnary - 解锁密码库")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(16)

        title = QLabel("Accnary")
        title.setProperty("title", True)
        layout.addWidget(title)
        subtitle = QLabel("个人账号与密码管理器 - 本地 KDBX 加密存储")
        subtitle.setProperty("muted", True)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # recent vaults (hidden when a path was given)
        self.recent_list: QListWidget | None = None
        self._recent_paths: list[str] = []
        if vault_path is None:
            self._recent_paths = load_recent_paths()
            if self._recent_paths:
                recent_header = QLabel("最近使用的密码库")
                recent_header.setProperty("section", True)
                layout.addWidget(recent_header)
                self.recent_list = QListWidget()
                self.recent_list.setMaximumHeight(88)
                for p in self._recent_paths:
                    self.recent_list.addItem(p)
                self.recent_list.currentTextChanged.connect(
                    self._on_recent_selected
                )
                layout.addWidget(self.recent_list)

        form = QFormLayout()
        form.setSpacing(8)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(
            vault_path
            or (
                self._recent_paths[0]
                if self._recent_paths
                else default_vault_path()
            )
        )
        self.path_edit.setObjectName("vaultPath")
        self.path_edit.setPlaceholderText("密码库文件路径 (.kdbx)")
        self.path_edit.setClearButtonEnabled(True)
        self.path_edit.setToolTip(self.path_edit.text())
        self.path_edit.textChanged.connect(self.path_edit.setToolTip)
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse_btn)
        form.addRow("密码库", path_row)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("主密码")
        form.addRow("主密码", self.password_edit)

        # create-only fields (hidden unless creating)
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setPlaceholderText("再输入一次主密码")
        self.confirm_label = QLabel("确认主密码")
        form.addRow(self.confirm_label, self.confirm_edit)
        self.confirm_label.setVisible(False)
        self.confirm_edit.setVisible(False)

        layout.addLayout(form)

        self.master_password_hint = QLabel(
            "主密码无法找回。请在安全的离线位置留存纸面副本；加密库备份不能替代主密码。"
        )
        self.master_password_hint.setProperty("warning", True)
        self.master_password_hint.setAccessibleName("主密码无法找回提示")
        self.master_password_hint.setWordWrap(True)
        self.master_password_hint.hide()
        layout.addWidget(self.master_password_hint)

        self.error_label = QLabel("")
        self.error_label.setProperty("error", True)
        self.error_label.setAccessibleName("错误提示")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.create_mode = False
        self.create_btn = QPushButton("创建新的密码库…")
        self.create_btn.setProperty("variant", "ghost")
        self.create_btn.clicked.connect(self._toggle_create)
        layout.addWidget(self.create_btn, 0, Qt.AlignmentFlag.AlignLeft)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.unlock_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.unlock_button.setText("解锁")
        self.unlock_button.setProperty("variant", "primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("退出")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.password_edit.setFocus()

    # ------------------------------------------------------------------ UI

    def _toggle_create(self) -> None:
        self.create_mode = not self.create_mode
        creating = self.create_mode
        self.master_password_hint.setVisible(creating)
        self.confirm_label.setVisible(creating)
        self.confirm_edit.setVisible(creating)
        self.unlock_button.setText("创建" if creating else "解锁")
        self.create_btn.setText("使用现有密码库…" if creating else "创建新的密码库…")
        if creating:
            try:
                path_suffix = resolve_vault_path(self.path_edit.text()).suffix.lower()
            except ValueError:
                path_suffix = ".kdbx"
            if path_suffix != ".kdbx":
                self.path_edit.setText(default_vault_path())
        self.error_label.setText("")

    def _browse(self) -> None:
        if self.create_mode:
            try:
                initial_path = resolve_vault_path(
                    self.path_edit.text() or default_vault_path()
                )
            except ValueError as exc:
                self.error_label.setText(str(exc))
                return
            path, _ = QFileDialog.getSaveFileName(
                self,
                "新建密码库",
                str(initial_path),
                "KeePass 数据库 (*.kdbx)",
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择密码库", str(Path.home()), "KeePass 数据库 (*.kdbx)"
            )
        if path:
            self.path_edit.setText(path)

    def _on_recent_selected(self, text: str) -> None:
        if self.recent_list is not None and self.recent_list.hasFocus():
            self.path_edit.setText(text)

    # ---------------------------------------------------------------- logic

    def _on_accept(self) -> None:
        if self.create_mode:
            self._create()
        else:
            self._unlock()

    def done(self, result) -> None:
        self.password_edit.clear()
        self.confirm_edit.clear()
        super().done(result)

    def _unlock(self) -> None:
        raw_path = self.path_edit.text().strip()
        password = self.password_edit.text()
        if not raw_path:
            self.error_label.setText("请填写密码库路径。")
            return
        try:
            path = resolve_vault_path(raw_path)
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return
        try:
            self.catalog = run_storage_task(
                self, "正在解锁密码库…", lambda: CatalogService.open(str(path), password)
            )
        except BadCredentialsError:
            self.error_label.setText("主密码不正确，请重试。")
            self.password_edit.selectAll()
            self.password_edit.setFocus()
            return
        except VaultFormatError as exc:
            self.error_label.setText(f"文件无法读取（损坏或不是 KDBX 库）：\n{exc}")
            return
        except VaultError as exc:
            self.error_label.setText(str(exc))
            return
        except Exception as exc:  # defensive: never crash on odd vault states
            self.error_label.setText(f"打开失败：{type(exc).__name__}: {exc}")
            return
        remember_recent_path(str(path))
        self.accept()

    def _create(self) -> None:
        raw_path = self.path_edit.text().strip()
        password = self.password_edit.text()
        if not raw_path:
            self.error_label.setText("请填写新密码库的保存路径。")
            return
        if password != self.confirm_edit.text():
            self.error_label.setText("两次输入的主密码不一致。")
            return
        if len(password) < 8:
            self.error_label.setText("主密码至少需要 8 个字符。")
            return
        try:
            path = resolve_vault_path(raw_path)
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return
        if path.exists():
            self.error_label.setText("目标文件已存在，请换一个文件名。")
            return
        try:
            self.catalog = run_storage_task(
                self,
                "正在创建并校验加密密码库…",
                lambda: CatalogService.create_vault(str(path), password),
            )
        except AccnaryError as exc:
            self.error_label.setText(f"创建失败：{exc}")
            return
        except Exception as exc:  # defensive
            self.error_label.setText(f"创建失败：{type(exc).__name__}: {exc}")
            return
        remember_recent_path(str(path))
        self.accept()
