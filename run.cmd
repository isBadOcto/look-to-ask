@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please install Python 3.12 and follow README.md setup steps first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -m look_to_ask %*
if errorlevel 1 pause
