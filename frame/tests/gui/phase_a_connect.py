"""GUI black-box test support: launch a private Accnary instance and drive it
with pywinauto (UIA backend) on the real Windows desktop.

Phase A script: connect + dump the unlock dialog control tree + screenshot.
All data is fictional; the test vault goes to a temp directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

FRAME = Path(__file__).resolve().parents[2]
SHOTS = FRAME / ".gui-shots"
SHOTS.mkdir(exist_ok=True)
PYTHONW = FRAME / ".venv" / "Scripts" / "pythonw.exe"
LOG = SHOTS / "app-log.txt"


def launch_app() -> subprocess.Popen:
    log_handle = open(LOG, "w", encoding="utf-8")
    env = os.environ.copy()
    # fully isolated instance: own APPDATA -> own QSettings ini (no shared
    # recent-vaults list, nothing written to the user's real config)
    env["APPDATA"] = str(SHOTS / "appdata")
    Path(env["APPDATA"]).mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [str(PYTHONW), "main.py"],
        cwd=str(FRAME),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return proc


def _child_pids(pid: int) -> list[int]:
    """One level of direct children (the venv pythonw stub spawns the real one)."""
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' "
            "| Select-Object -ExpandProperty ProcessId",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return [int(x) for x in result.stdout.split() if x.strip().isdigit()]


def main() -> None:
    from pywinauto import Desktop

    proc = launch_app()
    print(f"launched pid={proc.pid}")
    desktop = Desktop(backend="uia")

    window = None
    target_pids = {proc.pid}
    for _ in range(60):
        time.sleep(0.5)
        target_pids |= set(_child_pids(proc.pid))
        for pid in target_pids:
            try:
                candidate = desktop.window(process=pid, title_re="Accnary.*")
                if candidate.exists(timeout=0.1):
                    window = candidate
                    break
            except Exception:
                continue
        if window is not None:
            break
    if window is None:
        print("FAIL: no Accnary window found (pids tried:", target_pids, ")")
        sys.exit(1)

    window.set_focus()
    time.sleep(1)
    print("window title:", window.window_text())
    print("visible:", window.is_visible())
    img = window.capture_as_image()
    img.save(SHOTS / "01-unlock-dialog.png")
    print("--- control tree ---")
    window.print_control_identifiers(depth=4)
    print(f"screenshot: {SHOTS / '01-unlock-dialog.png'}")


if __name__ == "__main__":
    main()
