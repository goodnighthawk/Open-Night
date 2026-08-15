@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\spatial_interest_audit.py
) else (
  python tools\spatial_interest_audit.py
)
pause
