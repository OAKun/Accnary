"""Phase B: create a vault through the real unlock dialog, land on the main
window, dump its control tree, screenshot, and keep the instance running
(session state saved for phase C)."""

from __future__ import annotations

import json
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
SESSION = SHOTS / "session.json"

VAULT = SHOTS / "test-vault.kdbx"
MASTER_PASSWORD = "GuiTest-Master-123"


def _child_pids(pid: int) -> list[int]:
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' "
            "| Select-Object -ExpandProperty ProcessId",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return [int(x) for x in result.stdout.split() if x.strip().isdigit()]


def launch():
    log_handle = open(LOG, "w", encoding="utf-8")
    env = os.environ.copy()
    env["APPDATA"] = str(SHOTS / "appdata")
    Path(env["APPDATA"]).mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [str(PYTHONW), "main.py"], cwd=str(FRAME),
        stdout=log_handle, stderr=subprocess.STDOUT, env=env,
    )


def find_window(desktop, proc):
    target_pids = {proc.pid}
    for _ in range(60):
        time.sleep(0.5)
        target_pids |= set(_child_pids(proc.pid))
        for pid in target_pids:
            try:
                candidate = desktop.window(process=pid, title_re="Accnary.*")
                if candidate.exists(timeout=0.1):
                    return candidate, pid
            except Exception:
                continue
    return None, None


def main() -> None:
    from pywinauto import Desktop

    if VAULT.exists():
        VAULT.unlink()

    proc = launch()
    print(f"launched pid={proc.pid}")
    desktop = Desktop(backend="uia")

    window, _pid = find_window(desktop, proc)
    if window is None:
        print("FAIL: unlock window not found; log:")
        print(LOG.read_text(encoding="utf-8", errors="replace")[:2000])
        sys.exit(1)
    print("unlock window:", window.window_text())
    window.set_focus()
    time.sleep(0.8)

    # --- create-vault flow ------------------------------------------------
    window.child_window(title="创建新的密码库…", control_type="Button").click_input()
    time.sleep(0.6)
    edits = window.descendants(control_type="Edit")
    print(f"edits visible: {len(edits)}")
    # 0 = path, 1 = master password, 2 = confirmation
    edits[0].set_edit_text(str(VAULT))
    edits[1].set_edit_text(MASTER_PASSWORD)
    edits[2].set_edit_text(MASTER_PASSWORD)
    ok_btn = window.child_window(
        auto_id="QApplication.UnlockDialog.QDialogButtonBox.QPushButton",
        control_type="Button", found_index=0,
    )
    print("ok button text:", ok_btn.window_text())
    ok_btn.click_input()

    # --- wait for the main window ------------------------------------------
    main_window = None
    target_pids = {proc.pid} | set(_child_pids(proc.pid))
    for _ in range(40):
        time.sleep(0.5)
        target_pids |= set(_child_pids(proc.pid))
        for pid in target_pids:
            try:
                candidate = desktop.window(
                    process=pid, title="Accnary", control_type="Window"
                )
                if candidate.exists(timeout=0.1):
                    main_window = candidate
                    break
            except Exception:
                continue
        if main_window is not None:
            break
    if main_window is None:
        # diagnose: is the unlock dialog still open? what does it say?
        try:
            unlock = desktop.window(process=proc.pid, title_re="Accnary.*")
            if unlock.exists(timeout=0.5):
                unlock.capture_as_image().save(SHOTS / "fail-unlock-still-open.png")
                print("FAIL: unlock dialog still open; error label:")
                for label in unlock.descendants(control_type="Text"):
                    t = label.window_text().strip()
                    if t:
                        print("  text:", t)
        except Exception:
            pass
        print("app log:")
        print(LOG.read_text(encoding="utf-8", errors="replace")[:3000])
        sys.exit(1)
    print("main window reached:", main_window.window_text())
    time.sleep(1.0)
    main_window.set_focus()
    main_window.capture_as_image().save(SHOTS / "02-main-window.png")
    print("--- main window control tree ---")
    main_window.print_control_identifiers(depth=3)

    SESSION.write_text(
        json.dumps(
            {
                "launcher_pid": proc.pid,
                "vault": str(VAULT),
                "password": MASTER_PASSWORD,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"session saved; instance left running. shots: {SHOTS}")


if __name__ == "__main__":
    main()
