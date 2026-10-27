# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 21:13
# @Modified  : 2026-10-26 01:12
# @Python    : 3.14.9
# @Description: Accnary app / ui / recycle_bin_dialog
"""Recycle bin dialog: list trashed Accnary accounts and restore them."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from app.errors import AccnaryError
from app.models.serialization import entry_meta_from_json, META_CUSTOM_KEY
from app.services import CatalogService
from app.ui.storage_task import run_storage_task


class RecycleBinDialog(QDialog):
    def __init__(self, catalog: CatalogService, parent=None, on_changed=None):
        super().__init__(parent)
        self._catalog = catalog
        self._on_changed = on_changed  # callback after a successful restore
        self.setWindowTitle("回收站")
        self.setMinimumSize(480, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        hint = QLabel("删除的账户在这里保留，选中后可恢复到原平台。")
        hint.setProperty("muted", True)
        layout.addWidget(hint)

        self.content_stack = QStackedWidget()
        self.list_widget = QListWidget()
        self.empty_label = QLabel(
            "回收站为空\n已删除的账户会显示在这里，方便日后恢复。"
        )
        self.empty_label.setProperty("muted", True)
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_stack.addWidget(self.list_widget)
        self.content_stack.addWidget(self.empty_label)
        layout.addWidget(self.content_stack, 1)

        self.error_label = QLabel("")
        self.error_label.setProperty("error", True)
        self.error_label.setAccessibleName("错误提示")
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        self.restore_button = QPushButton("恢复选中账户")
        self.restore_button.setProperty("variant", "primary")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._restore)
        self.list_widget.currentItemChanged.connect(
            lambda current, _previous: self.restore_button.setEnabled(
                current is not None
            )
        )
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(self.restore_button)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self._refresh()

    def _refresh(self) -> None:
        self.list_widget.clear()
        kp = self._catalog.vault.kp
        recycle_bin = kp.recyclebin_group
        if recycle_bin is not None:
            for entry in recycle_bin.entries:
                meta_json = entry.custom_properties.get(META_CUSTOM_KEY)
                if meta_json is None:
                    continue  # non-Accnary trashed entries stay untouched
                try:
                    _service, account = entry_meta_from_json(meta_json)
                except AccnaryError:
                    continue
                label = account.alias or entry.username or "（未命名账户）"
                item = QListWidgetItem(f"{entry.title}  ·  {label}")
                item.setData(Qt.ItemDataRole.UserRole, str(entry.uuid))
                self.list_widget.addItem(item)
        self.content_stack.setCurrentWidget(
            self.list_widget if self.list_widget.count() else self.empty_label
        )

    def _restore(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            self.error_label.setText("请先选择要恢复的账户。")
            return
        uuid = item.data(Qt.ItemDataRole.UserRole)
        try:
            with self._catalog.mutation():
                self._catalog.restore_account(uuid)
                run_storage_task(self, "正在安全保存密码库…", self._catalog.save)
        except AccnaryError as exc:
            self.error_label.setText(f"恢复失败：{exc}")
            return
        self.error_label.setText("")
        self._refresh()
        if self._on_changed is not None:
            self._on_changed()
