"""Phase C: create an account through the editor dialog, verify the list +
detail panel, copy the password to the clipboard. Instance from phase B
must still be running (session.json)."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

FRAME = Path(__file__).resolve().parents[2]
SHOTS = FRAME / ".gui-shots"
SESSION = json.loads((SHOTS / "session.json").read_text(encoding="utf-8"))


def _clipboard() -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout.rstrip("\r\n")


def _texts_of(widget) -> list[str]:
    return [w.window_text() for w in widget.descendants(control_type="Text")
            if w.window_text().strip()]


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


def _my_window(desktop) -> object:
    """The main window of MY instance (user's instance has the same title)."""
    pids = {SESSION["launcher_pid"]}
    first_level = _child_pids(SESSION["launcher_pid"])
    pids |= set(first_level)
    for child in first_level:
        pids |= set(_child_pids(child))
    for pid in pids:
        try:
            candidate = desktop.window(process=pid, title="Accnary", control_type="Window")
            if candidate.exists(timeout=0.1):
                return candidate
        except Exception:
            continue
    return None


def main() -> None:
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    main_window = _my_window(desktop)
    assert main_window is not None, "my instance's main window not found"
    main_window.set_focus()
    time.sleep(0.5)

    # ---- open the editor ---------------------------------------------------
    main_window.child_window(title="新建账户", control_type="Button").click_input()
    editor = None
    for _ in range(20):
        time.sleep(0.5)
        try:
            candidate = desktop.window(
                title="新建账户", control_type="Window"
            )
            if candidate.exists(timeout=0.1):
                editor = candidate
                break
        except Exception:
            continue
    if editor is None:
        print("FAIL: editor dialog not found")
        raise SystemExit(1)
    editor.set_focus()
    time.sleep(0.5)
    print("editor open")

    edits = editor.descendants(control_type="Edit")
    print(f"editor edits: {len(edits)}")
    for i, e in enumerate(edits):
        try:
            print(f"  edit[{i}]: value={e.window_text()!r}")
        except Exception:
            pass
    # order (basic form, deterministic): 0=platform combo inner edit,
    # 1=username, 2=password, 3=url, 4=email, 5=phone
    edits[0].set_edit_text("测试云盘")
    edits[1].set_edit_text("gui-user")
    edits[2].set_edit_text("GuiPassword-9")
    edits[3].set_edit_text("https://pan.example.com/login")

    save_btn = editor.child_window(title="保存", control_type="Button")
    save_btn.click_input()
    time.sleep(1.0)

    # editor should be gone; main window list shows the account
    try:
        if editor.exists(timeout=0.5):
            print("FAIL: editor still open; error label texts:")
            for t in _texts_of(editor):
                print("  ", t)
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception:
        pass

    print("PASS: editor closed after save")
    time.sleep(0.5)
    main_window.capture_as_image().save(SHOTS / "03-account-created.png")

    row_texts = _texts_of(main_window)
    print("window texts:", [t for t in row_texts if "测试云盘" in t or "gui-user" in t])
    assert any("测试云盘" in t for t in row_texts), "account row missing"
    assert any("gui-user" in t for t in row_texts), "username missing"
    print("PASS: account row visible in list")

    # ---- select the row -> detail panel ------------------------------------
    lists = main_window.descendants(control_type="List")
    print(f"lists found: {len(lists)}")
    account_list = None
    for lst in lists:
        items = lst.descendants(control_type="ListItem")
        if items and "测试云盘" in items[0].window_text():
            account_list = lst
            break
    if account_list is None:
        print("FAIL: account list item not found")
        raise SystemExit(1)
    account_list.descendants(control_type="ListItem")[0].click_input()
    time.sleep(0.8)
    main_window.capture_as_image().save(SHOTS / "04-detail-panel.png")

    detail_texts = _texts_of(main_window)
    assert any("凭据" in t for t in detail_texts), "detail credentials card missing"
    assert any("登录方式" in t for t in detail_texts), "login methods card missing"
    print("PASS: detail panel rendered")

    # ---- reveal + copy password ---------------------------------------------
    show_btn = None
    for btn in main_window.descendants(control_type="Button"):
        if btn.window_text() == "显示":
            show_btn = btn
            break
    assert show_btn is not None, "password reveal button missing"
    show_btn.click_input()
    time.sleep(0.4)
    detail_texts = _texts_of(main_window)
    assert any("GuiPassword-9" in t for t in detail_texts), "password not revealed"
    print("PASS: password reveal works")

    copy_btn = None
    for btn in main_window.descendants(control_type="Button"):
        if btn.window_text() == "复制":
            copy_btn = btn
            break
    copy_btn.click_input()
    time.sleep(0.6)
    clip = _clipboard()
    assert clip == "GuiPassword-9", f"clipboard mismatch: {clip!r}"
    print("PASS: copy password -> clipboard verified")

    print("ALL PHASE C CHECKS PASSED")


if __name__ == "__main__":
    main()
