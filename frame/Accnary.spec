# -*- mode: python ; coding: utf-8 -*-
"""Accnary PyInstaller spec - the ONLY sanctioned way to build the EXE.

Per AGENTS.md: entry-point imports were inspected; only the runtime paths
are bundled (PySide6-Essentials, pykeepass + crypto deps). Everything else
is explicitly excluded so an accidental import can't bloat the release.

Layout: SINGLE-FILE EXE (user decision). The payload extracts itself to a
temp dir on each launch and cleans up on exit - no user data is ever placed
there; the vault lives wherever the user saved it.

Build with:  .venv/Scripts/python build_exe.py
"""

import os
import pykeepass

project_root = os.path.abspath(SPECPATH)

# Agent document/PDF tool runtimes can prepend unrelated ICU/UCRT copies
# to PATH. They are not application dependencies; use Qt's own DLLs and
# the Windows system runtime rather than collecting those tool binaries.
_tool_runtime = os.path.normcase(os.path.join(os.path.expanduser("~"), ".cache", "codex-runtimes"))
os.environ["PATH"] = os.pathsep.join(
    item for item in os.environ.get("PATH", "").split(os.pathsep)
    if not os.path.normcase(os.path.abspath(item.strip('"'))).startswith(_tool_runtime + os.sep)
)

# Qt submodules the app demonstrably does not use (Widgets-only app):
_qt_excludes = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtTest", "PySide6.QtConcurrent",
    "PySide6.QtSql", "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtXml", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtHelp", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtSensors",
]

# Qt standard-button Chinese translation (loaded via QLibraryInfo at runtime)
_pyside_translations = os.path.join(
    project_root, ".venv", "Lib", "site-packages", "PySide6", "translations"
)
_keepass_template = os.path.join(
    os.path.dirname(pykeepass.__file__), "blank_database.kdbx"
)
if not os.path.isfile(_keepass_template):
    raise FileNotFoundError(f"missing PyKeePass database template: {_keepass_template}")

_datas = [
    (os.path.join(project_root, "assets", "app-icon.png"), "assets"),
    (_keepass_template, "pykeepass"),
]
if os.path.isdir(_pyside_translations):
    for _name in ("qt_zh_CN.qm", "qtbase_zh_CN.qm"):
        _source = os.path.join(_pyside_translations, _name)
        if os.path.isfile(_source):
            _datas.append((_source, "PySide6/translations"))

a = Analysis(
    ["main.py"],
    pathex=[project_root],
    binaries=[],
    datas=_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_qt_excludes
    + [
        "tkinter",
        "unittest",
        "pydoc_data",
        "setuptools",
        "pip",
        "pytest",
        "pip_audit",
        "pywinauto",
        "PIL",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Accnary",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX on a credential manager invites AV false positives
    runtime_tmpdir=None,
    console=False,  # windowed application
    icon=os.path.join(project_root, "assets", "app-icon.ico"),
)
