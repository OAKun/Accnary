# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-27 11:13
# @Modified  : 2026-10-27 11:27
# @Python    : 3.14
# @Description: 通过 ToolHub manifest 检查 Accnary 新版（SemVer 判定），并流式下载校验新版程序
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QIODevice, QObject, QSaveFile, QUrl, Signal
from PySide6.QtCore import QSettings
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkProxyFactory,
    QNetworkReply,
    QNetworkRequest,
)


app_id = "accnary"
app_name = "Accnary"
# 本地版本号由产品自身的唯一版本源提供（见 tools.json 的 version_from），
# 生成器不再写入副本，避免两处版本真相漂移。

# 统一版本真相源：ToolHub 仓库 main 分支的 manifest.json。
manifest_url = "https://cnb.cool/oakun/ToolHub/-/git/raw/main/manifest.json"
# 兼容地址：latest Release 附件中的 manifest.json（发布端同步提供）。
manifest_url_fallback = (
    "https://cnb.cool/oakun/ToolHub/-/releases/download/latest/manifest.json"
)
manifest_urls: list[str] = [manifest_url, manifest_url_fallback]
manifest_urls_env_name = "ACCNARY_UPDATE_MANIFEST_URLS"

# 自动检查节流：24 小时最多一次；手动检查（manual=True）不受此限制。
auto_check_interval = timedelta(hours=24)
_qsettings_org = "OAKun"
_qsettings_app = "Accnary"
_last_check_key = "update/last_check_at"


@dataclass(frozen=True)
class UpdateInfo:
    remote_version: str
    remote_sha256: str
    download_url: str
    notes: str


@dataclass(frozen=True)
class UpdateSource:
    kind: Literal["manifest"]
    name: str
    url: str


def file_sha256_text(file_path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _configure_redirects(request: QNetworkRequest) -> None:
    """允许 HTTPS 下载地址的安全跳转。"""
    try:
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
    except (AttributeError, TypeError):
        # 仅兼容不含该枚举的旧版 Qt；其它异常不应被静默忽略。
        return


def _normalize_url(url: str) -> str:
    return url.strip()


def validate_https_download_url(url: str) -> str:
    """自动更新只接受有效的 HTTPS 下载地址。"""
    url = _normalize_url(url)
    parsed_url = QUrl(url)
    if not parsed_url.isValid() or parsed_url.scheme().lower() != "https":
        raise ValueError(f"自动更新下载地址不是有效的 HTTPS URL：{url!r}")
    return url


def _env_manifest_urls() -> list[str]:
    raw = os.environ.get(manifest_urls_env_name, "")
    return [url.strip() for url in raw.split(";") if url.strip()]


def parse_version(text: str) -> tuple[int, int, int]:
    """把 SemVer（MAJOR.MINOR.PATCH）解析为可比较的三元组，拒绝其它格式。"""
    parts = text.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"不是合法 SemVer：{text!r}")
    numbers: list[int] = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"不是合法 SemVer：{text!r}")
        numbers.append(int(part))
    return numbers[0], numbers[1], numbers[2]


def is_newer_version(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def sha256_from_text(text: str) -> str:
    match = re.search(r"(?i)\b[a-f0-9]{64}\b", text)
    if not match:
        raise ValueError("未找到有效的 sha256。")
    return match.group(0).lower()


def parse_manifest_json(text: str, want_app_id: str) -> UpdateInfo | None:
    """解析 ToolHub 统一 manifest.json，返回当前 app 的更新信息；无记录返回 None。"""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("manifest.json 不是 JSON 对象。")
    if data.get("schema_version") != 1:
        raise ValueError(f"不支持的 manifest schema_version：{data.get('schema_version')!r}")

    apps = data.get("apps")
    if not isinstance(apps, dict):
        raise ValueError("manifest.json 缺少 apps。")
    entry = apps.get(want_app_id)
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise ValueError(f"manifest 中 {want_app_id} 记录非法。")

    remote_version = entry.get("version")
    if not isinstance(remote_version, str) or not remote_version.strip():
        raise ValueError(f"manifest 中 {want_app_id} 缺少 version。")

    asset = entry.get("asset")
    if not isinstance(asset, dict):
        raise ValueError(f"manifest 中 {want_app_id} 缺少 asset。")
    url = asset.get("url")
    sha256 = asset.get("sha256")
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"manifest 中 {want_app_id} asset.url 缺失。")
    if not isinstance(sha256, str) or not sha256.strip():
        raise ValueError(f"manifest 中 {want_app_id} asset.sha256 缺失。")

    notes = entry.get("notes") or ""
    if not isinstance(notes, str):
        notes = str(notes)

    return UpdateInfo(
        remote_version=remote_version.strip(),
        remote_sha256=sha256_from_text(sha256),
        download_url=validate_https_download_url(url),
        notes=notes,
    )


class UpdateChecker(QObject):
    update_available = Signal(object)
    no_update = Signal(bool)
    check_failed = Signal(bool)
    check_failed_with_message = Signal(bool, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        QNetworkProxyFactory.setUseSystemConfiguration(True)
        self.manager = QNetworkAccessManager(self)
        self.local_version = ""
        self.manual = False
        self._sources: list[UpdateSource] = []
        self._source_index = 0
        self._errors: list[str] = []
        self._check_generation = 0
        self._candidate_update: UpdateInfo | None = None

    def check(self, local_version: str, manual: bool = False) -> None:
        self._check_generation += 1
        generation = self._check_generation
        self.local_version = local_version.strip()
        self.manual = manual
        self._source_index = 0
        self._errors = []
        self._sources = self._build_sources()
        self._candidate_update = None

        if not manual and not self._auto_check_due():
            self.no_update.emit(manual)
            return

        try:
            parse_version(self.local_version)
        except ValueError:
            self._fail(manual, f"本地版本号不是合法 SemVer: {self.local_version!r}")
            return

        self._try_next_source(generation)

    @staticmethod
    def _settings() -> QSettings:
        isolated = os.environ.get("ACCNARY_SETTINGS_DIR")
        if isolated:
            return QSettings(str(Path(isolated) / "Accnary.ini"), QSettings.Format.IniFormat)
        return QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            "Accnary",
            "Accnary",
        )

    def _auto_check_due(self) -> bool:
        settings = self._settings()
        last_text = settings.value(_last_check_key, "", type=str).strip()
        if not last_text:
            return True
        try:
            last = datetime.fromisoformat(last_text)
        except ValueError:
            return True
        return datetime.now() - last >= auto_check_interval

    def _mark_check_completed(self) -> None:
        settings = self._settings()
        settings.setValue(_last_check_key, datetime.now().isoformat(timespec="seconds"))

    def _build_sources(self) -> list[UpdateSource]:
        sources: list[UpdateSource] = []
        seen: set[str] = set()
        for url in [*manifest_urls, *_env_manifest_urls()]:
            url = _normalize_url(url)
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append(UpdateSource("manifest", "manifest.json", url))
        return sources

    def _try_next_source(self, generation: int) -> None:
        if generation != self._check_generation:
            return
        if self._source_index >= len(self._sources):
            if self._candidate_update is not None:
                self._mark_check_completed()
                self.update_available.emit(self._candidate_update)
                return
            detail = "\n".join(self._errors) if self._errors else "没有可用的更新源。"
            self._fail(self.manual, f"所有更新源均访问失败：\n{detail}")
            return

        source = self._sources[self._source_index]
        self._source_index += 1

        request = QNetworkRequest(QUrl(source.url))
        request.setRawHeader(b"User-Agent", b"Accnary-update-checker")
        request.setRawHeader(b"Cache-Control", b"no-cache")
        request.setRawHeader(b"Accept", b"application/json,text/plain,*/*")
        request.setTransferTimeout(15000)
        _configure_redirects(request)

        reply = self.manager.get(request)
        reply.finished.connect(
            lambda reply=reply, source=source, generation=generation: self._handle_reply(
                reply,
                source,
                generation,
            )
        )

    def _record_error(self, source: UpdateSource, message: str) -> None:
        self._errors.append(f"[{source.name}] {message}")

    def _fail(self, manual: bool, message: str) -> None:
        self.check_failed_with_message.emit(manual, message)
        self.check_failed.emit(manual)

    def _handle_reply(
        self,
        reply: QNetworkReply,
        source: UpdateSource,
        generation: int,
    ) -> None:
        try:
            if generation != self._check_generation:
                return
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            error = reply.error()
            raw = bytes(reply.readAll())

            if error != QNetworkReply.NetworkError.NoError:
                self._record_error(
                    source,
                    f"HTTP={status}, error={error}, message={reply.errorString()}",
                )
                self._try_next_source(generation)
                return

            if isinstance(status, int) and status >= 400:
                preview = raw[:300].decode("utf-8", errors="replace")
                self._record_error(source, f"HTTP={status}, 返回内容预览={preview!r}")
                self._try_next_source(generation)
                return

            text = raw.decode("utf-8", errors="strict")
            info = parse_manifest_json(text, app_id)

            # 清单里没有本应用记录，视为已最新（不强制更新）。
            if info is None:
                self._candidate_update = None
                self._mark_check_completed()
                self.no_update.emit(self.manual)
                return

            if not is_newer_version(info.remote_version, self.local_version):
                self._candidate_update = None
                self._mark_check_completed()
                self.no_update.emit(self.manual)
                return

            if self._candidate_update is None:
                self._candidate_update = info
            self._try_next_source(generation)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._record_error(source, f"解析失败: {exc}")
            self._try_next_source(generation)
            return
        finally:
            reply.deleteLater()


class UpdateDownloader(QObject):
    """将新版 EXE 流式写入临时文件，并在提交前校验 SHA-256。"""

    progress = Signal(int, int)
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        QNetworkProxyFactory.setUseSystemConfiguration(True)
        self.manager = QNetworkAccessManager(self)
        self.reply: QNetworkReply | None = None
        self._save_file: QSaveFile | None = None
        self._destination: Path | None = None
        self._expected_sha256 = ""
        self._hasher = hashlib.sha256()
        self._bytes_written = 0
        self._cancel_requested = False
        self._write_error = ""

    @property
    def is_running(self) -> bool:
        return self.reply is not None

    def start(
        self,
        download_url: str,
        destination: str | Path,
        expected_sha256: str,
    ) -> None:
        if self.is_running:
            raise RuntimeError("更新下载任务已经在运行。")

        expected_sha256 = expected_sha256.strip().lower()
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise ValueError("远端 sha256 格式不正确。")

        destination = Path(destination)
        save_file = QSaveFile(str(destination))
        if not save_file.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(f"无法创建更新临时文件：{destination}")

        self._save_file = save_file
        self._destination = destination
        self._expected_sha256 = expected_sha256
        self._hasher = hashlib.sha256()
        self._bytes_written = 0
        self._cancel_requested = False
        self._write_error = ""

        download_qurl = QUrl(download_url)
        if (
            not download_qurl.isValid()
            or download_qurl.scheme().lower() not in {"https", "file"}
        ):
            self._cancel_file()
            self._reset()
            raise ValueError("更新下载地址必须使用 HTTPS。")

        request = QNetworkRequest(download_qurl)
        request.setRawHeader(b"User-Agent", b"Accnary-update-downloader")
        request.setRawHeader(b"Accept", b"application/octet-stream,*/*")
        request.setRawHeader(b"Cache-Control", b"no-cache")
        request.setTransferTimeout(60000)
        _configure_redirects(request)

        reply = self.manager.get(request)
        self.reply = reply
        reply.readyRead.connect(self._write_available_data)
        reply.downloadProgress.connect(self.progress.emit)
        reply.finished.connect(self._handle_finished)

    def cancel(self) -> None:
        if self.reply is None:
            return
        self._cancel_requested = True
        self.reply.abort()

    def _write_available_data(self) -> None:
        if self.reply is None or self._save_file is None or self._write_error:
            return
        data = self.reply.readAll()
        if data.isEmpty():
            return

        raw = bytes(data)
        written = self._save_file.write(data)
        if written != len(raw):
            self._write_error = self._save_file.errorString() or "写入更新文件失败。"
            self.reply.abort()
            return
        self._hasher.update(raw)
        self._bytes_written += len(raw)

    def _cancel_file(self) -> None:
        if self._save_file is not None:
            self._save_file.cancelWriting()

    def _reset(self) -> None:
        self.reply = None
        self._save_file = None
        self._destination = None
        self._expected_sha256 = ""
        self._bytes_written = 0
        self._cancel_requested = False
        self._write_error = ""

    def _handle_finished(self) -> None:
        reply = self.reply
        save_file = self._save_file
        destination = self._destination
        if reply is None or save_file is None or destination is None:
            return

        self._write_available_data()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        network_error = reply.error()
        error_message = ""

        if self._cancel_requested:
            self._cancel_file()
        elif self._write_error:
            error_message = self._write_error
            self._cancel_file()
        elif network_error != QNetworkReply.NetworkError.NoError:
            error_message = f"下载失败：{reply.errorString()}"
            self._cancel_file()
        elif isinstance(status, int) and status >= 400:
            error_message = f"下载失败：HTTP {status}"
            self._cancel_file()
        elif self._bytes_written <= 0:
            error_message = "下载文件为空，已拒绝安装。"
            self._cancel_file()
        elif self._hasher.hexdigest() != self._expected_sha256:
            error_message = "下载文件的 SHA-256 与发布信息不一致，已拒绝安装。"
            self._cancel_file()
        elif not save_file.commit():
            error_message = save_file.errorString() or "无法提交更新临时文件。"
            save_file.cancelWriting()

        cancelled = self._cancel_requested
        completed_path = str(destination)
        reply.deleteLater()
        self._reset()

        if cancelled:
            self.cancelled.emit()
        elif error_message:
            destination.unlink(missing_ok=True)
            self.failed.emit(error_message)
        else:
            self.completed.emit(completed_path)
