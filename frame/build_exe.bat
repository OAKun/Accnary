@echo off
rem Accnary build launcher (family convention: build_exe.bat + X.bat + .spec).
rem One double-click: build the single-file EXE, verify it on the desktop,
rem place it into ..\release\ with its SHA-256, and clean intermediates.
rem If this project's Accnary.exe is running, the build stops without closing it.
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" build_exe.py
echo.
pause
