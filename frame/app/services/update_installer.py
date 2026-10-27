# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-27 11:13
# @Modified  : 2026-10-27 11:27
# @Python    : 3.14
# @Description: 安全替换 Accnary.exe，确认新版启动、回滚并清理更新残留
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path


installer_dir_prefix = "Accnary-update-installer-"
ready_file_name = "update.ready"
update_ready_env_name = "ACCNARY_UPDATE_READY_FILE"


updater_script = r"""
param(
    [Parameter(Mandatory = $true)][string]$TargetPath,
    [Parameter(Mandatory = $true)][string]$StagedPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $true)][int]$ParentProcessId,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][int]$ReadyTimeoutSeconds
)

$ErrorActionPreference = "Stop"
$replaced = $false
$backupPath = ""
$targetDirectory = [System.IO.Path]::GetDirectoryName($TargetPath)
$scriptDirectory = [System.IO.Path]::GetDirectoryName($PSCommandPath)
$readyPath = Join-Path $scriptDirectory "update.ready"

# PyInstaller 6.9+ 中，同路径 onefile EXE 重启必须显式作为新实例解包。
$env:PYINSTALLER_RESET_ENVIRONMENT = "1"
$env:ACCNARY_UPDATE_READY_FILE = $readyPath

function Write-UpdateLog([string]$Message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Value "$timestamp $Message" -Encoding UTF8
}

function Wait-ForParentProcess {
    try {
        $parentProcess = [System.Diagnostics.Process]::GetProcessById($ParentProcessId)
        $parentProcess.WaitForExit(120000) | Out-Null
    }
    catch [System.ArgumentException] {
        return
    }
}

function Get-Sha256Hex([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha256.ComputeHash($stream)
        return [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Remove-UpdateArtifact([string]$Path, [int]$TimeoutSeconds) {
    $deadline = [System.DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ($true) {
        try {
            if (-not (Test-Path -LiteralPath $Path)) {
                return
            }
            Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
            return
        }
        catch [System.IO.IOException] {
        }
        catch [System.UnauthorizedAccessException] {
        }
        catch [System.Management.Automation.ItemNotFoundException] {
            return
        }

        if ([System.DateTime]::UtcNow -ge $deadline) {
            Write-UpdateLog "Cleanup deferred until the next Accnary start: $Path"
            return
        }
        Start-Sleep -Milliseconds 500
    }
}

try {
    Wait-ForParentProcess

    $fullTargetPath = [System.IO.Path]::GetFullPath($TargetPath)
    $fullStagedPath = [System.IO.Path]::GetFullPath($StagedPath)
    $fullTargetDirectory = [System.IO.Path]::GetDirectoryName($fullTargetPath)
    $fullStagedDirectory = [System.IO.Path]::GetDirectoryName($fullStagedPath)
    if (-not [string]::Equals(
        $fullTargetDirectory,
        $fullStagedDirectory,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "The staged update is not beside the target executable."
    }

    $actualSha256 = Get-Sha256Hex $fullStagedPath
    if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "The staged update checksum changed before installation."
    }

    $backupPath = Join-Path $fullTargetDirectory (
        ".Accnary.update-backup-" + [System.Guid]::NewGuid().ToString("N") + ".exe"
    )
    $deadline = [System.DateTime]::UtcNow.AddSeconds(120)
    $lastReplaceError = ""
    while (-not $replaced -and [System.DateTime]::UtcNow -lt $deadline) {
        try {
            [System.IO.File]::Replace(
                $fullStagedPath,
                $fullTargetPath,
                $backupPath,
                $true
            )
            $replaced = $true
        }
        catch [System.IO.IOException] {
            $lastReplaceError = $_.Exception.Message
            Start-Sleep -Milliseconds 500
        }
        catch [System.UnauthorizedAccessException] {
            $lastReplaceError = $_.Exception.Message
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $replaced) {
        throw "The old executable did not become replaceable: $lastReplaceError"
    }

    Remove-Item -LiteralPath $readyPath -Force -ErrorAction SilentlyContinue
    $newProcess = Start-Process `
        -FilePath $fullTargetPath `
        -WorkingDirectory $fullTargetDirectory `
        -PassThru
    if ($null -eq $newProcess) {
        throw "The updated application could not be started."
    }

    $readyDeadline = [System.DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    while (-not (Test-Path -LiteralPath $readyPath -PathType Leaf)) {
        if ($newProcess.HasExited) {
            throw "The updated application exited before reporting ready."
        }
        if ([System.DateTime]::UtcNow -ge $readyDeadline) {
            throw "The updated application did not report ready in time."
        }
        Start-Sleep -Milliseconds 200
        $newProcess.Refresh()
    }

    $readyProcessIdText = (Get-Content -LiteralPath $readyPath -Raw).Trim()
    $readyProcessId = 0
    if (-not [int]::TryParse($readyProcessIdText, [ref]$readyProcessId)) {
        throw "The updated application wrote an invalid ready marker."
    }
    try {
        $readyProcess = [System.Diagnostics.Process]::GetProcessById($readyProcessId)
    }
    catch [System.ArgumentException] {
        throw "The updated application exited during startup."
    }
    Start-Sleep -Seconds 2
    $readyProcess.Refresh()
    if ($readyProcess.HasExited) {
        throw "The updated application exited during startup."
    }

    Remove-UpdateArtifact -Path $backupPath -TimeoutSeconds 30
    Remove-Item -LiteralPath $readyPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $LogPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $scriptDirectory -Force -ErrorAction SilentlyContinue
    exit 0
}
catch {
    $failureMessage = $_.Exception.Message
    Write-UpdateLog "Update failed: $failureMessage"

    if ($replaced -and $backupPath -and (Test-Path -LiteralPath $backupPath)) {
        try {
            if (Test-Path -LiteralPath $TargetPath) {
                Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
                    try {
                        if ([string]::Equals(
                            $_.Path,
                            $TargetPath,
                            [System.StringComparison]::OrdinalIgnoreCase
                        )) {
                            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
                        }
                    }
                    catch {
                    }
                }
                Start-Sleep -Milliseconds 500
                [System.IO.File]::Delete($TargetPath)
            }
            [System.IO.File]::Move($backupPath, $TargetPath)
            $replaced = $false
            Write-UpdateLog "The previous executable was restored."
        }
        catch {
            Write-UpdateLog "Restore failed: $($_.Exception.Message)"
        }
    }

    Remove-Item -LiteralPath $StagedPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $readyPath -Force -ErrorAction SilentlyContinue
    Remove-Item Env:ACCNARY_UPDATE_READY_FILE -ErrorAction SilentlyContinue
    if (-not $replaced -and (Test-Path -LiteralPath $TargetPath)) {
        Start-Process -FilePath $TargetPath -WorkingDirectory $targetDirectory -ErrorAction SilentlyContinue
    }

    try {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            "Accnary could not install the update. The old version was kept or restored.`n`nLog: $LogPath",
            "Accnary update failed",
            [System.Windows.MessageBoxButton]::OK,
            [System.Windows.MessageBoxImage]::Warning
        ) | Out-Null
    }
    catch {
        Write-UpdateLog "Unable to show the failure dialog."
    }
    exit 1
}
"""


def write_update_ready_marker() -> bool:
    """在主窗口初始化后通知外部更新器。"""
    raw_path = os.environ.pop(update_ready_env_name, "").strip()
    if not raw_path:
        return False

    try:
        ready_path = Path(raw_path).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        installer_dir = ready_path.parent
        if (
            ready_path.name != ready_file_name
            or installer_dir.parent != temp_root
            or not installer_dir.name.startswith(installer_dir_prefix)
            or installer_dir.is_symlink()
            or installer_dir.is_junction()
            or ready_path.is_symlink()
        ):
            return False
        ready_path.write_text(f"{os.getpid()}\n", encoding="ascii")
    except OSError:
        return False
    return True


def cleanup_stale_update_files(
    target_path: str | Path,
    *,
    include_backups: bool = True,
) -> tuple[int, list[str]]:
    """清理自己遗留的下载、回滚备份和更新器临时目录。"""
    target_path = Path(target_path).resolve()
    if not target_path.is_file() or target_path.suffix.lower() != ".exe":
        raise ValueError(f"更新目标不是有效的 EXE：{target_path}")

    removed_count = 0
    errors: list[str] = []
    staged_name_pattern = re.compile(
        rf"\.{re.escape(target_path.stem)}\.update-[a-f0-9]{{32}}\.exe(?:\..+)?",
        re.IGNORECASE,
    )
    for candidate in target_path.parent.glob(f".{target_path.stem}.update-*.exe*"):
        if not staged_name_pattern.fullmatch(candidate.name):
            continue
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            candidate.unlink()
            removed_count += 1
        except FileNotFoundError:
            continue
        except OSError as error:
            errors.append(f"{candidate}: {error}")

    if include_backups:
        backup_name_pattern = re.compile(
            rf"\.{re.escape(target_path.stem)}\.update-backup-[a-f0-9]{{32}}\.exe",
            re.IGNORECASE,
        )
        for candidate in target_path.parent.glob(
            f".{target_path.stem}.update-backup-*.exe"
        ):
            if not backup_name_pattern.fullmatch(candidate.name):
                continue
            try:
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                candidate.unlink()
                removed_count += 1
            except FileNotFoundError:
                continue
            except OSError as error:
                errors.append(f"{candidate}: {error}")

    temp_root = Path(tempfile.gettempdir()).resolve()
    for installer_dir in temp_root.glob(f"{installer_dir_prefix}*"):
        try:
            if (
                not installer_dir.is_dir()
                or installer_dir.is_symlink()
                or installer_dir.is_junction()
            ):
                continue
        except OSError as error:
            errors.append(f"{installer_dir}: {error}")
            continue

        for filename in ("install_update.ps1", "update.log", ready_file_name):
            candidate = installer_dir / filename
            try:
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                candidate.unlink()
                removed_count += 1
            except FileNotFoundError:
                continue
            except OSError as error:
                errors.append(f"{candidate}: {error}")

        try:
            installer_dir.rmdir()
            removed_count += 1
        except FileNotFoundError:
            continue
        except OSError as error:
            errors.append(f"{installer_dir}: {error}")

    return removed_count, errors


def create_staged_update_path(target_path: str | Path) -> Path:
    """确认软件目录可写，并返回与目标 EXE 同目录的唯一临时路径。"""
    target_path = Path(target_path).resolve()
    if not target_path.is_file() or target_path.suffix.lower() != ".exe":
        raise ValueError(f"更新目标不是有效的 EXE：{target_path}")

    test_path = target_path.parent / f".{target_path.stem}.write-test-{uuid.uuid4().hex}.tmp"
    try:
        with test_path.open("xb"):
            pass
    except OSError as error:
        raise PermissionError(f"软件目录不可写：{target_path.parent}") from error
    finally:
        test_path.unlink(missing_ok=True)

    return target_path.parent / (
        f".{target_path.stem}.update-{uuid.uuid4().hex}{target_path.suffix}"
    )


def validate_update_paths(target_path: str | Path, staged_path: str | Path) -> None:
    """限制更新器只能用同目录临时 EXE 替换目标程序。"""
    target_path = Path(target_path).resolve()
    staged_path = Path(staged_path).resolve()
    expected_prefix = f".{target_path.stem}.update-".lower()

    if not target_path.is_file() or target_path.suffix.lower() != ".exe":
        raise ValueError(f"更新目标不是有效的 EXE：{target_path}")
    if not staged_path.is_file() or staged_path.suffix.lower() != ".exe":
        raise ValueError(f"更新临时文件不是有效的 EXE：{staged_path}")
    if staged_path.parent != target_path.parent:
        raise ValueError("更新临时文件必须与目标 EXE 位于同一目录。")
    if not staged_path.name.lower().startswith(expected_prefix):
        raise ValueError("更新临时文件名不符合安全规则。")


def launch_external_updater(
    target_path: str | Path,
    staged_path: str | Path,
    expected_sha256: str,
    parent_process_id: int,
    ready_timeout_seconds: int = 60,
) -> subprocess.Popen[bytes]:
    """启动独立更新脚本；调用方应持有返回对象直至当前程序退出。"""
    target_path = Path(target_path).resolve()
    staged_path = Path(staged_path).resolve()
    expected_sha256 = expected_sha256.strip().lower()
    validate_update_paths(target_path, staged_path)
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("远端 sha256 格式不正确。")
    if not 1 <= ready_timeout_seconds <= 120:
        raise ValueError("新版启动等待时间必须为 1–120 秒。")

    powershell_path = shutil.which("powershell.exe")
    if powershell_path is None:
        raise RuntimeError("系统中未找到 powershell.exe，无法自动安装更新。")

    updater_dir = Path(tempfile.mkdtemp(prefix=installer_dir_prefix))
    script_path = updater_dir / "install_update.ps1"
    log_path = updater_dir / "update.log"
    script_path.write_text(updater_script, encoding="utf-8-sig")

    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = subprocess.SW_HIDE
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    try:
        process = subprocess.Popen(
            [
                powershell_path,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-TargetPath",
                str(target_path),
                "-StagedPath",
                str(staged_path),
                "-ExpectedSha256",
                expected_sha256,
                "-ParentProcessId",
                str(parent_process_id),
                "-LogPath",
                str(log_path),
                "-ReadyTimeoutSeconds",
                str(ready_timeout_seconds),
            ],
            cwd=target_path.parent,
            close_fds=True,
            creationflags=creation_flags,
            startupinfo=startup_info,
        )
    except OSError:
        shutil.rmtree(updater_dir, ignore_errors=True)
        raise
    return process
