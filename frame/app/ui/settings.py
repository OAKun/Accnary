# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 20:14
# @Modified  : 2026-10-24 23:49
# @Python    : 3.14.9
# @Description: Accnary isolated preferences storage
"""Application preferences storage.

PySide6 gotcha: QSettings('org', 'app') binds its format parameter to
NativeFormat (the Windows registry) regardless of setDefaultFormat, so the
constructor must name the format explicitly. Preferences live as an INI file
under %APPDATA%\\Accnary\\Accnary.ini - never the registry.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings

_ORG = "Accnary"
_APP = "Accnary"


def app_settings() -> QSettings:
    # Process-local override for isolated source/EXE verification. Normal
    # launches keep the established APPDATA preference location unchanged.
    isolated = os.environ.get("ACCNARY_SETTINGS_DIR")
    if isolated:
        return QSettings(str(Path(isolated) / "Accnary.ini"), QSettings.Format.IniFormat)
    return QSettings(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, _ORG, _APP
    )
