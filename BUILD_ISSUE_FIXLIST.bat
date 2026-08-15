@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\issue_fixlist.py
) else (
  python tools\issue_fixlist.py
)
echo.
echo Reports are stored persistently under Documents\PythonMMO_SharedData\issue_reports
pause
