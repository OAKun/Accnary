# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-27 11:12
# @Modified  : 2026-10-27 11:15
# @Python    : 3.14.9
# @Description: Accnary startup and manual ToolHub update checks with confirmed installation.

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget

from app.services.update_installer import (
    cleanup_stale_update_files,
    create_staged_update_path,
    launch_external_updater,
)
from app.services.update_service import UpdateChecker, UpdateDownloader, UpdateInfo
from app.ui.settings import app_settings
from app.version import APP_VERSION

startup_check_delay_ms = 2500


class UpdateFlow(QObject):
    busy_changed = Signal(bool)

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._checker: UpdateChecker | None = None
        self._downloader: UpdateDownloader | None = None
        self._check_progress: QProgressDialog | None = None
        self._download_progress: QProgressDialog | None = None
        self._staged_path: Path | None = None
        self._target_path: Path | None = None
        self._updater_process: subprocess.Popen[bytes] | None = None
        self._pending_update: UpdateInfo | None = None

    @staticmethod
    def is_packaged() -> bool:
        return bool(getattr(sys, "frozen", False))

    @property
    def busy(self) -> bool:
        return self._checker is not None or self._downloader is not None

    def start_auto_checks(self, *, skip_initial: bool = False) -> None:
        if not self.is_packaged():
            return
        try:
            cleanup_stale_update_files(sys.executable)
        except (OSError, ValueError):
            pass
        if not skip_initial:
            QTimer.singleShot(startup_check_delay_ms, self._check_if_enabled)

    def _check_if_enabled(self) -> None:
        if app_settings().value("update/auto_check", True, type=bool):
            self.check(manual=False)

    def check(self, manual: bool) -> None:
        if not self.is_packaged():
            if manual:
                QMessageBox.information(
                    self._window,
                    "检查更新",
                    "当前为源码运行，检查更新仅在已发布的 Accnary.exe 中可用。",
                )
            return
        if self.busy:
            if manual:
                QMessageBox.information(self._window, "检查更新", "更新检查正在进行，请稍候。")
            return

        checker = UpdateChecker(self)
        self._checker = checker
        checker.update_available.connect(self._on_update_available)
        checker.no_update.connect(self._on_no_update)
        checker.check_failed_with_message.connect(self._on_check_failed)
        self.busy_changed.emit(True)
        if manual:
            self._show_check_progress()
        checker.check(APP_VERSION, manual=manual)

    def _show_check_progress(self) -> None:
        progress = QProgressDialog("正在检查更新…", None, 0, 0, self._window)
        progress.setWindowTitle("检查更新")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(400)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setCancelButton(None)
        self._check_progress = progress
        progress.show()

    def _finish_check(self) -> None:
        if self._check_progress is not None:
            self._check_progress.close()
            self._check_progress.deleteLater()
            self._check_progress = None
        if self._checker is not None:
            self._checker.deleteLater()
            self._checker = None
        self.busy_changed.emit(False)

    def _on_update_available(self, info: UpdateInfo) -> None:
        self._finish_check()
        self._pending_update = info
        self._show_update_prompt_when_ready()

    def _show_update_prompt_when_ready(self) -> None:
        info = self._pending_update
        if info is None:
            return
        app = QApplication.instance()
        if app is None or not self._window.isVisible():
            return
        if app.activeModalWidget() is not None or getattr(self._window, "_storage_busy", False):
            QTimer.singleShot(500, self._show_update_prompt_when_ready)
            return

        self._pending_update = None
        notes = info.notes.strip()
        if len(notes) > 1800:
            notes = notes[:1800].rstrip() + "…"
        notes_text = f"\n\n更新说明：\n{notes}" if notes else ""
        answer = QMessageBox.question(
            self._window,
            "发现 Accnary 更新",
            f"当前版本 v{APP_VERSION}，发现 v{info.remote_version}。"
            f"{notes_text}\n\n现在下载并更新程序？密码库文件不会被更新。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._download_and_install(info)

    def _on_no_update(self, manual: bool) -> None:
        self._finish_check()
        if manual:
            QMessageBox.information(
                self._window, "检查更新", f"当前已是最新版本 v{APP_VERSION}。"
            )

    def _on_check_failed(self, manual: bool, message: str) -> None:
        self._finish_check()
        if manual:
            QMessageBox.warning(self._window, "检查更新失败", f"请稍后再试。\n\n{message}")

    def _download_and_install(self, info: UpdateInfo) -> None:
        target_path = Path(sys.executable).resolve()
        try:
            staged_path = create_staged_update_path(target_path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                self._window,
                "无法自动更新",
                f"程序目录不可写：{error}\n\n将打开新版下载地址，可手动替换 Accnary.exe。",
            )
            QDesktopServices.openUrl(QUrl(info.download_url))
            return

        progress = QProgressDialog("正在下载新版 Accnary.exe…", "取消", 0, 0, self._window)
        progress.setWindowTitle("下载并安装更新")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        downloader = UpdateDownloader(self)
        self._downloader = downloader
        self._download_progress = progress
        self._staged_path = staged_path
        self._target_path = target_path
        self.busy_changed.emit(True)
        downloader.progress.connect(self._show_download_progress)
        progress.canceled.connect(downloader.cancel)
        downloader.cancelled.connect(self._on_download_cancelled)
        downloader.failed.connect(self._on_download_failed)
        downloader.completed.connect(lambda path: self._on_download_completed(path, info))
        try:
            downloader.start(
                download_url=info.download_url,
                destination=staged_path,
                expected_sha256=info.remote_sha256,
            )
        except (OSError, RuntimeError, ValueError) as error:
            self._drop_staged_file()
            self._release_download_ui()
            QMessageBox.warning(self._window, "无法开始下载", str(error))
            return
        progress.show()

    def _show_download_progress(self, received: int, total: int) -> None:
        progress = self._download_progress
        if progress is None:
            return
        progress.setLabelText(
            f"正在下载新版 Accnary.exe… 已下载 {received / 1024 / 1024:.1f} MB"
        )
        if total > 0:
            progress.setRange(0, 1000)
            progress.setValue(min(1000, int(received * 1000 / total)))

    def _drop_staged_file(self) -> None:
        if self._staged_path is not None:
            try:
                self._staged_path.unlink(missing_ok=True)
            except OSError:
                # A leftover staged EXE is safely removed by the next startup.
                pass

    def _release_download_ui(self) -> None:
        if self._download_progress is not None:
            self._download_progress.close()
            self._download_progress.deleteLater()
            self._download_progress = None
        if self._downloader is not None:
            self._downloader.deleteLater()
            self._downloader = None
        self._staged_path = None
        self.busy_changed.emit(False)

    def _on_download_cancelled(self) -> None:
        self._drop_staged_file()
        self._release_download_ui()

    def _on_download_failed(self, message: str) -> None:
        self._drop_staged_file()
        self._release_download_ui()
        QMessageBox.warning(self._window, "更新失败", f"{message}\n\n当前版本保持不变。")

    def _on_download_completed(self, downloaded_path: str, info: UpdateInfo) -> None:
        staged_path = Path(downloaded_path).resolve()
        progress = self._download_progress
        if progress is not None:
            progress.setRange(0, 0)
            progress.setLabelText("正在准备安装…")
        try:
            self._updater_process = launch_external_updater(
                target_path=self._target_path,
                staged_path=staged_path,
                expected_sha256=info.remote_sha256,
                parent_process_id=os.getpid(),
            )
        except (OSError, RuntimeError, ValueError) as error:
            self._drop_staged_file()
            self._release_download_ui()
            QMessageBox.warning(self._window, "无法启动更新器", str(error))
            return

        self._release_download_ui()
        if self._window.close():
            return

        self._stop_updater_process()
        staged_path.unlink(missing_ok=True)
        QMessageBox.information(
            self._window,
            "更新已取消",
            "程序退出未完成，更新没有安装；当前版本继续运行。",
        )

    def _stop_updater_process(self) -> None:
        process = self._updater_process
        self._updater_process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
