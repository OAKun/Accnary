"""Check startup boundaries in fresh processes, before Qt imports are cached."""

import os
from pathlib import Path
import subprocess
import sys


def _run_fresh(source):
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-B", "-c", source],
        cwd=Path(__file__).resolve().parents[2],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_unlock_import_does_not_load_workspace():
    _run_fresh('''
import sys
from app.ui.unlock_dialog import UnlockDialog
assert "app.ui.main_window" not in sys.modules
assert "app.ui.account_editor" not in sys.modules
from app.ui import MainWindow
from app.ui.main_window import MainWindow as direct
assert MainWindow is direct
from app.ui import UnlockDialog as exported
assert UnlockDialog is exported
''')


def test_cancelled_startup_does_not_import_workspace():
    _run_fresh('''
import sys
import main
import app.ui.unlock_dialog as unlock_module
from PySide6.QtWidgets import QDialog

class CancelledUnlock:
    DialogCode = QDialog.DialogCode
    catalog = None
    def exec(self):
        return QDialog.DialogCode.Rejected

unlock_module.UnlockDialog = CancelledUnlock
app = main._build_app()
assert main.run_gui() == 0
assert "app.ui.main_window" not in sys.modules
assert "app.ui.account_editor" not in sys.modules
''')
