@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" map_viewer.py %*
) else (
  py map_viewer.py %*
)
if errorlevel 1 pause
