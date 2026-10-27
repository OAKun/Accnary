# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 23:00
# @Modified  : 2026-10-27 11:40
# @Python    : 3.14.9
# @Description: Accnary Windows EXE build, verification, and release workflow.
"""Accnary Windows build script - the documented, fixed release path.

Usage:
  .venv/Scripts/python build_exe.py                 Build, verify, and promote.
  .venv/Scripts/python build_exe.py --validate-only Build and keep in dist/.
  .venv/Scripts/python build_exe.py --promote       Promote a validated dist/ build.

Steps (Caday/Finance family convention):
1. convert assets/app-icon.png -> assets/app-icon.ico (PyInstaller needs ico)
2. refuse to continue while this project's Accnary.exe is running
3. run PyInstaller with the committed Accnary.spec (single-file, no ad-hoc flags)
4. verify: EXE exists, size + SHA-256, real-desktop GUI launch, --check exit code
5. --validate-only retains the staged EXE; --promote verifies its manifest then updates release/
6. clean build/dist/__pycache__ intermediates after promotion

Output: ../release/Accnary.exe (single file; version embedded in the app).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FRAME = Path(__file__).resolve().parent
DIST = FRAME / "dist"
EXE = DIST / "Accnary.exe"
RELEASE_DIR = FRAME.parent / "release"
RELEASE_EXE = RELEASE_DIR / "Accnary.exe"
VALIDATION_MANIFEST = DIST / ".accnary-validation.json"


def _running_project_instances() -> list[tuple[int, str]]:
    """List running processes whose executable is this project's Accnary."""
    if os.name != "nt":
        return []
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='Accnary.exe'\" "
        "| ForEach-Object { if ($_.ExecutablePath) "
        "{ Write-Output \"$($_.ProcessId)`t$($_.ExecutablePath)\" } }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise SystemExit("could not check running Accnary processes; build stopped safely")

    targets = {
        os.path.normcase(str(EXE.resolve())),
        os.path.normcase(str(RELEASE_EXE.resolve())),
    }
    running = []
    for line in result.stdout.splitlines():
        process_id, separator, image_path = line.partition("\t")
        if not separator:
            continue
        try:
            pid = int(process_id)
            resolved = os.path.normcase(str(Path(image_path).resolve()))
        except (OSError, ValueError):
            continue
        if resolved in targets:
            running.append((pid, image_path))
    return running


def _require_no_running_instances() -> None:
    running = _running_project_instances()
    if running:
        details = ", ".join(f"PID {pid}: {path}" for pid, path in running)
        raise SystemExit(
            "Accnary is running from this project; close it manually and retry. "
            f"No process was terminated. ({details})"
        )


def _source_fingerprint() -> str:
    """Hash the application and packaging inputs represented by a build."""
    files = [
        FRAME / "main.py",
        FRAME / "Accnary.spec",
        FRAME / "build_exe.py",
        FRAME / "requirements-lock.txt",
        FRAME / "assets" / "app-icon.png",
        FRAME / "assets" / "app-icon.ico",
    ]
    files.extend(sorted((FRAME / "app").rglob("*.py")))
    files.extend(sorted((FRAME / "tests").rglob("*.py")))
    digest = hashlib.sha256()
    for path in files:
        if not path.is_file():
            raise SystemExit(f"build input missing: {path}")
        digest.update(path.relative_to(FRAME).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _app_version() -> str:
    import ast

    version_path = FRAME / "app" / "version.py"
    tree = ast.parse(version_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "APP_VERSION"
            for target in node.targets
        ):
            return str(ast.literal_eval(node.value))
    raise SystemExit(f"APP_VERSION was not found in {version_path.relative_to(FRAME)}")


def _write_validation_manifest() -> None:
    manifest = {
        "version": _app_version(),
        "exe_sha256": hashlib.sha256(EXE.read_bytes()).hexdigest(),
        "source_fingerprint": _source_fingerprint(),
        "gui_smoke": "passed",
        "self_check": "passed",
    }
    VALIDATION_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"validation manifest: {VALIDATION_MANIFEST}")


def _verify_validation_manifest() -> None:
    if not EXE.is_file() or not VALIDATION_MANIFEST.is_file():
        raise SystemExit("no staged validation build found; build with --validate-only first")
    try:
        manifest = json.loads(VALIDATION_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"staged validation manifest is unreadable: {type(exc).__name__}") from exc
    current_hash = hashlib.sha256(EXE.read_bytes()).hexdigest()
    if manifest.get("version") != _app_version():
        raise SystemExit("staged EXE version does not match current source; promotion refused")
    if manifest.get("exe_sha256") != current_hash:
        raise SystemExit("staged EXE changed after validation; promotion refused")
    if manifest.get("source_fingerprint") != _source_fingerprint():
        raise SystemExit("application source changed after validation; promotion refused")
    if manifest.get("gui_smoke") != "passed" or manifest.get("self_check") != "passed":
        raise SystemExit("staged EXE has no complete internal validation record")


def _write_sidecar(path: Path, digest: str) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    tmp = sidecar.with_name(sidecar.name + ".tmp")
    try:
        with tmp.open("w", encoding="ascii", newline="\n") as handle:
            handle.write(f"{digest}  {path.name}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, sidecar)
    finally:
        tmp.unlink(missing_ok=True)


def ensure_ico() -> Path:
    from PIL import Image

    png = FRAME / "assets" / "app-icon.png"
    ico = FRAME / "assets" / "app-icon.ico"
    if not png.is_file():
        raise SystemExit(f"missing source icon: {png}")
    if not ico.is_file() or png.stat().st_mtime > ico.stat().st_mtime:
        img = Image.open(png)
        img.save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print(f"icon generated: {ico.name}")
    return ico


def build() -> None:
    VALIDATION_MANIFEST.unlink(missing_ok=True)
    ensure_ico()
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "Accnary.spec", "--noconfirm", "--clean"],
        cwd=str(FRAME),
    )
    if result.returncode != 0 or not EXE.is_file():
        raise SystemExit("PyInstaller build FAILED")
    size_mb = EXE.stat().st_size / 1024 / 1024
    sha = hashlib.sha256(EXE.read_bytes()).hexdigest()
    print(f"EXE: {EXE}")
    print(f"exe size: {size_mb:.1f} MB (single file)")
    print(f"exe sha256: {sha}")


def check_exit_code() -> bool:
    """`Accnary.exe --check` must exit 0 (self_check passes inside the exe)."""
    result = subprocess.run(
        [str(EXE), "--check"],
        cwd=str(DIST),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    ok = result.returncode == 0
    print(f"--check via exe (exit code): {'PASS' if ok else f'FAIL ({result.returncode})'}")
    return ok


def _process_image_path(process_id: int) -> Path | None:
    """Return the exact executable path for a Windows process ID."""
    if os.name != "nt":
        return None

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(0x1000, False, process_id)
    if not handle:
        return None
    try:
        image = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(image))
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, image, ctypes.byref(length)
        ):
            return None
        return Path(image.value).resolve()
    finally:
        kernel32.CloseHandle(handle)


def gui_smoke() -> bool:
    """Real-desktop launch: the unlock window must appear.

    Onefile bootloader spawns a child process for the app, so match by its
    exact image path. Preferences are redirected to a temporary directory.
    """
    expected_exe = EXE.resolve()
    with tempfile.TemporaryDirectory(prefix="accnary-build-settings-") as settings_dir:
        env = os.environ.copy()
        env["ACCNARY_SETTINGS_DIR"] = settings_dir
        proc = subprocess.Popen([str(EXE)], cwd=str(DIST), env=env)
        smoke_pids = {proc.pid}
        try:
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            for _ in range(90):
                time.sleep(0.5)
                try:
                    candidates = [
                        w for w in desktop.windows(control_type="Window")
                        if w.window_text() in ("Accnary", "Accnary - 解锁密码库")
                    ]
                    for window in candidates:
                        process_id = window.process_id()
                        image_path = _process_image_path(process_id)
                        if image_path is None or os.path.normcase(
                            str(image_path)
                        ) != os.path.normcase(str(expected_exe)):
                            continue
                        smoke_pids.add(process_id)
                        return True
                except Exception:
                    continue
            return False
        finally:
            if os.name == "nt":
                # These PIDs were started by this smoke check; a child is
                # added only after its image path matches the staged EXE.
                for pid in smoke_pids:
                    image_path = _process_image_path(pid)
                    if image_path is None or os.path.normcase(
                        str(image_path)
                    ) != os.path.normcase(str(expected_exe)):
                        continue
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
            elif proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def finalize() -> Path:
    """Move the EXE to ../release/ and write the checksum (family layout:
    flat release dir, no version subfolder - the version lives in the app)."""
    _require_no_running_instances()
    RELEASE_DIR.mkdir(exist_ok=True)
    moved = EXE.replace(RELEASE_EXE)
    sha = hashlib.sha256(moved.read_bytes()).hexdigest()
    _write_sidecar(moved, sha)
    print(f"release: {RELEASE_EXE}")
    print(f"release sha256: {sha}")
    return moved


def cleanup(*, keep_dist: bool = False) -> None:
    """Remove build intermediates (keep release artifacts and user data)."""
    import shutil

    paths = (FRAME / "build",) if keep_dist else (DIST, FRAME / "build")
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    for cache in FRAME.rglob("__pycache__"):
        if ".venv" not in cache.parts and "tools" not in cache.parts:
            shutil.rmtree(cache, ignore_errors=True)
    cache = FRAME / ".pytest_cache"
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)


def _verify_staged_exe() -> None:
    failures = []
    if not gui_smoke():
        failures.append("gui")
    if not check_exit_code():
        failures.append("check")
    if failures:
        raise SystemExit(f"verification FAILED: {failures} (dist output kept for inspection)")
    _write_validation_manifest()


def _print_usage() -> None:
    print("Usage: build_exe.py [--validate-only | --promote]")


if __name__ == "__main__":
    modes = sys.argv[1:]
    if modes not in ([], ["--validate-only"], ["--promote"]):
        _print_usage()
        raise SystemExit(2)

    _require_no_running_instances()

    if modes == ["--promote"]:
        _verify_validation_manifest()
        if not check_exit_code():
            raise SystemExit("staged EXE self-check failed; release was not changed")
        finalize()
        cleanup()
        print("\nBuild promoted after staged validation:")
        print(f"  {RELEASE_EXE}")
        print(f"  {RELEASE_DIR / 'Accnary.exe.sha256'}")
    elif modes == ["--validate-only"]:
        build()
        _verify_staged_exe()
        cleanup(keep_dist=True)
        print(f"\nValidation build kept for external acceptance: {EXE}")
    else:
        build()
        _verify_staged_exe()
        finalize()
        cleanup()
        print("\nBuild finished:")
        print(f"  {RELEASE_EXE}")
        print(f"  {RELEASE_DIR / 'Accnary.exe.sha256'}")
