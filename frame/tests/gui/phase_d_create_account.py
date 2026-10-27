"""Phase D: keyboard-driven account creation.

Qt's UIA tree for owned modal dialogs is incomplete (known Qt accessibility
quirk), so the editor is driven by real keyboard input in deterministic Tab
order (matches widget creation order). The authoritative verification is
re-opening the vault file from disk afterwards.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pywinauto.keyboard as kb

from pywinauto import Desktop

FRAME = Path(__file__).resolve().parents[2]
SHOTS = FRAME / ".gui-shots"
SESSION = json.loads((SHOTS / "session.json").read_text(encoding="utf-8"))
MY_PID = 62552  # resolved GUI process (kept from session discovery)


def _gui_pid() -> int:
    launcher = SESSION["launcher_pid"]
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={launcher}' "
            "| Select-Object -ExpandProperty ProcessId",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return int(result.stdout.split()[0])


def _close_stray_editors() -> int:
    """Close every leftover editor dialog (WM_CLOSE = reject, never saves)."""
    win32 = Desktop(backend="win32")
    closed = 0
    for w in win32.windows():
        if "新建账户" in w.window_text():
            w.close()
            closed += 1
            time.sleep(0.5)
    return closed


def _editor_hwnd():
    win32 = Desktop(backend="win32")
    for w in win32.windows():
        if w.window_text() == "新建账户":
            return w.handle
    return None


def main() -> None:
    from pywinauto import Desktop
    from pywinauto.timings import wait_until

    gui_pid = _gui_pid()
    print("gui pid:", gui_pid)
    desktop = Desktop(backend="uia")

    # close the two stray editor dialogs from earlier attempts
    closed = _close_stray_editors()
    print(f"closed {closed} stray editor dialog(s)")

    main_window = desktop.window(process=gui_pid, title="Accnary", control_type="Window")
    main_window.set_focus()
    time.sleep(0.5)
    main_window.child_window(title="新建账户", control_type="Button").click_input()

    hwnd = wait_until(10, 0.5, _editor_hwnd)
    print("editor hwnd:", hwnd)
    uia_desktop = Desktop(backend="uia")
    editor = uia_desktop.window(handle=hwnd)
    editor.set_focus()
    time.sleep(0.6)
    editor.capture_as_image().save(SHOTS / "05-editor-before-typing.png")

    # Tab order (creation order): platform, type, alias, username,
    # [显示][生成], url, method, email, phone, notes, 更多选项
    kb.send_keys("{VK_CLEAR}")  # no-op guard
    kb.send_keys("测试云盘")  # platform combo edit (focused on open)
    kb.send_keys("{TAB}{TAB}")  # -> type combo -> alias (skip)
    kb.send_keys("{TAB}")  # -> username
    kb.send_keys("gui-user")
    kb.send_keys("{TAB}")  # -> password
    kb.send_keys("GuiPassword-9")
    kb.send_keys("{TAB}{TAB}")  # -> 显示 -> 生成… (do not trigger)
    kb.send_keys("{TAB}")  # -> url
    kb.send_keys("https://pan.example.com/login")
    kb.send_keys("{TAB}{TAB}{TAB}{TAB}")  # method, email, phone -> notes
    kb.send_keys("{TAB}")  # -> 更多选项 (do not toggle)
    editor.capture_as_image().save(SHOTS / "06-editor-filled.png")

    # Enter activates the dialog's default button (保存)
    kb.send_keys("{ENTER}")
    time.sleep(1.5)

    still_open = _editor_hwnd() is not None
    print("editor still open:", still_open)
    if still_open:
        editor2 = Desktop(backend="uia").window(handle=_editor_hwnd())
        editor2.capture_as_image().save(SHOTS / "fail-editor-after-enter.png")
        print("FAIL: editor did not close (validation error?)")
        raise SystemExit(1)

    print("PASS: editor accepted and closed")
    time.sleep(0.8)
    main_window.capture_as_image().save(SHOTS / "07-account-created.png")

    # --- authoritative verification: reopen the vault file -----------------
    sys_path = str(FRAME)
    check = subprocess.run(
        [
            str(FRAME / ".venv" / "Scripts" / "python.exe"), "-c",
            "import sys; sys.path.insert(0, r'%s');\n"
            "from app.services import CatalogService\n"
            "kp = CatalogService.open(r'%s', 'GuiTest-Master-123')\n"
            "accs = kp.catalog.all_accounts()\n"
            "print('ACCOUNTS:', [(a.username, a.password, a.primary_url) for a in accs])\n"
            "print('SERVICES:', [s.name for s in kp.catalog.services])\n"
            % (sys_path, SESSION["vault"]),
        ],
        capture_output=True, text=True, timeout=120,
    )
    print(check.stdout.strip())
    if check.returncode != 0:
        print("FAIL: vault reopen error:", check.stderr[-500:])
        raise SystemExit(1)
    if "gui-user" not in check.stdout or "GuiPassword-9" not in check.stdout:
        print("FAIL: account not persisted as typed")
        raise SystemExit(1)
    print("PASS: account persisted in the vault exactly as typed")

    SESSION["gui_pid"] = gui_pid
    (SHOTS / "session.json").write_text(json.dumps(SESSION, indent=1), encoding="utf-8")
    print("ALL PHASE D CHECKS PASSED")


if __name__ == "__main__":
    main()
