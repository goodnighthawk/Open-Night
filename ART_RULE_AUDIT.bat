@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\art_rule_audit.py
) else (
  python tools\art_rule_audit.py
)
if errorlevel 1 pause
endlocal
