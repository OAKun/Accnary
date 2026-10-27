# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 22:13
# @Modified  : 2026-10-27 11:15
# @Python    : 3.14.9
# @Description: Accnary main
"""Accnary entry point.

Modes:
  python main.py          normal start: unlock dialog -> main window
  python main.py --check  print the runtime stack versions and exit
  python main.py --smoke  assemble the full UI offscreen against a throwaway
                          vault, quit automatically (CI/startup verification)
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.version import APP_VERSION

VERSION_LABEL = f"{APP_VERSION} 首发版（未经独立第三方安全审计）"


def self_check() -> int:
    print(f"Accnary {APP_VERSION} (stack check)")
    print(f"python {sys.version.split()[0]} ({sys.executable})")

    try:
        import pykeepass

        print(f"pykeepass {pykeepass.__version__}")
    except Exception as exc:
        print(f"pykeepass import FAILED: {exc}")
        return 1

    try:
        from PySide6 import QtCore
        from PySide6 import __version__ as pyside_version

        print(f"PySide6 {pyside_version} / Qt {QtCore.qVersion()}")
    except Exception as exc:
        print(f"PySide6 import FAILED: {exc}")
        return 1

    print("stack OK")
    return 0


def _build_app():
    from PySide6.QtCore import QLibraryInfo, QTranslator
    from PySide6.QtWidgets import QApplication

    from app.ui import icons, theme
    from app.ui.settings import app_settings

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Accnary")
    app.setOrganizationName("Accnary")
    app.setWindowIcon(icons.app_icon())

    # localize Qt standard buttons (Yes/No/OK/Cancel -> 是/否/确定/取消)
    translations_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    translator = QTranslator(app)
    if translator.load(str(Path(translations_dir) / "qt_zh_CN.qm")):
        app.installTranslator(translator)

    saved_theme = str(app_settings().value("theme", "light"))
    settings = app_settings()
    if settings.contains("hotkey_enabled"):
        settings.remove("hotkey_enabled")
    theme.apply_theme(app, saved_theme)
    return app


def run_gui() -> int:
    import os

    from PySide6.QtCore import QTimer

    from app.services.update_installer import (
        update_ready_env_name,
        write_update_ready_marker,
    )
    from app.ui import MainWindow
    from app.ui.unlock_dialog import UnlockDialog

    app = _build_app()
    updated_start = bool(os.environ.get(update_ready_env_name))
    unlock = UnlockDialog()
    # Signal that the new EXE reached its modal unlock window. The updater can
    # then finalize its rollback copy without waiting for the user to unlock.
    QTimer.singleShot(0, write_update_ready_marker)
    if unlock.exec() != UnlockDialog.DialogCode.Accepted or unlock.catalog is None:
        return 0
    window = MainWindow(unlock.catalog)
    unlock.catalog = None
    unlock.deleteLater()
    window.show()
    window.update_flow.start_auto_checks(skip_initial=updated_start)
    return app.exec()


def run_smoke() -> int:
    """Assemble the full UI offscreen against a throwaway vault, then quit."""
    import os
    import tempfile
    previous_settings_dir = os.environ.get("ACCNARY_SETTINGS_DIR")
    app = catalog = window = None

    with tempfile.TemporaryDirectory(prefix="accnary-smoke-") as tmp:
        os.environ["ACCNARY_SETTINGS_DIR"] = str(Path(tmp) / "settings")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            app = _build_app()

            from PySide6.QtCore import QTimer

            from app.models import Account
            from app.services import CatalogService
            from app.ui import MainWindow

            vault_path = Path(tmp) / "smoke.kdbx"
            catalog = CatalogService.create_vault(vault_path, "smoke-pass-1234")
            service = catalog.add_service("SmokeCloud")
            catalog.add_account(
                service, Account(username="smoke-user", password="smoke-pw")
            )
            catalog.save()

            window = MainWindow(catalog)
            window.show()
            result = {"code": 1}

            def finish():
                assert window.account_list.count() == 1, (
                    "account list must show the seed account"
                )
                result["code"] = 0
                app.quit()

            QTimer.singleShot(400, finish)
            app.exec()
            print(f"smoke {'OK' if result['code'] == 0 else 'FAILED'}")
            return result["code"]
        finally:
            if window is not None:
                window.close()
            if catalog is not None and not catalog.is_locked:
                catalog.lock()
            if app is not None:
                app.processEvents()
            if previous_settings_dir is None:
                os.environ.pop("ACCNARY_SETTINGS_DIR", None)
            else:
                os.environ["ACCNARY_SETTINGS_DIR"] = previous_settings_dir


if __name__ == "__main__":
    if "--check" in sys.argv:
        raise SystemExit(self_check())
    if "--smoke" in sys.argv:
        raise SystemExit(run_smoke())
    raise SystemExit(run_gui())
