# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 23:36
# @Modified  : 2026-10-25 23:45
# @Python    : 3.14.9
# @Description: Expose existing encrypted backup and restore services through an explicit local Qt workflow.
from pathlib import Path

from PySide6.QtWidgets import (QDialog, QFileDialog, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout)

from app.errors import AccnaryError
from app.services import CatalogService
from app.storage import export_backup, restore_from_backup
from app.ui.storage_task import run_storage_task


class BackupDialog(QDialog):
    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self._catalog = catalog
        self.restored_catalog = None
        self.setWindowTitle("数据与备份")
        self.setMinimumWidth(530)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        title = QLabel("数据与备份")
        title.setProperty("pageTitle", True)
        layout.addWidget(title)
        path = QLineEdit(str(catalog.path))
        path.setReadOnly(True)
        path.setToolTip(str(catalog.path))
        layout.addWidget(path)
        hint = QLabel("备份保留 KDBX 加密。旧备份需要使用创建该备份时的主密码。\n"
                      "每次保存还会保留同目录 .bak 快照，建议另外保存一份异地备份。")
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        layout.addWidget(hint)
        export = QPushButton("导出加密备份…")
        export.setProperty("variant", "primary")
        export.clicked.connect(self._export)
        layout.addWidget(export)
        restore = QPushButton("从加密备份恢复…")
        restore.clicked.connect(self._restore)
        layout.addWidget(restore)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def _export(self):
        destination, _ = QFileDialog.getSaveFileName(
            self, "导出加密备份", str(self._catalog.path.with_stem(self._catalog.path.stem + "-backup")),
            "KeePass 加密数据库 (*.kdbx)",
        )
        if not destination:
            return
        try:
            def export():
                if self._catalog.has_unsaved_changes:
                    self._catalog.save()
                return export_backup(self._catalog.vault, destination)

            run_storage_task(self, "正在校验并导出加密备份…", export)
        except (AccnaryError, OSError) as exc:
            self.status_label.setText(f"备份未完成：{exc}")
            return
        self.status_label.setText("加密备份已保存，并已重新打开校验。")

    def _restore(self):
        source, _ = QFileDialog.getOpenFileName(
            self, "选择加密备份", str(self._catalog.path.parent),
            "KeePass 加密数据库 (*.kdbx *.bak);;所有文件 (*)",
        )
        if not source:
            return
        password, accepted = QInputDialog.getText(
            self, "验证备份", "请输入这份备份的主密码", QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return
        # Validate before the final overwrite confirmation, using a read-only
        # catalog load; format/schema safeguards are retained after restoration.
        try:
            def validate_backup():
                probe = CatalogService.open(source, password)
                probe.lock()

            run_storage_task(self, "正在验证加密备份…", validate_backup)
        except (AccnaryError, OSError):
            self.status_label.setText("备份无法验证：请检查文件和该备份的主密码。")
            return
        answer = QMessageBox.question(
            self, "确认恢复密码库",
            f"备份：{Path(source).name}\n将替换当前库：{self._catalog.path}\n\n"
            "恢复前会保存 .pre-restore.bak 快照。确认继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.restored_catalog = run_storage_task(
                self,
                "正在恢复并校验密码库…",
                lambda: CatalogService(
                    restore_from_backup(
                        self._catalog.path, source, password, confirmed=True
                    )
                ),
            )
        except (AccnaryError, OSError) as exc:
            self.status_label.setText(f"恢复未完成：{exc}")
            return
        finally:
            password = ""  # release our reference; not a claim of memory erasure
        self.accept()
