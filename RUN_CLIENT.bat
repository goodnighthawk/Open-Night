@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OPEN NIGHT - Desktop Client

if not exist ".venv\Scripts\python.exe" (
  echo Preparing the Open Night Python environment...
  call START_HERE.bat --setup-only
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo [ERROR] The Python environment was not created.
  echo Review the setup error above.
  pause
  exit /b 2
)

set "CLIENT_LOG=%~dp0client_crash.log"
set "PYTHONFAULTHANDLER=1"
set "PYTHONUNBUFFERED=1"

echo Open Night desktop client starting...
echo If it fails, this window will remain open and show the traceback.
echo Crash log: %CLIENT_LOG%
echo.

".venv\Scripts\python.exe" -u client.py >"%CLIENT_LOG%" 2>&1
set "CLIENT_RC=%ERRORLEVEL%"

if "%CLIENT_RC%"=="0" (
  echo Client closed normally.
  exit /b 0
)

echo.
echo ============================================================
echo [CLIENT CRASH] Exit code %CLIENT_RC%
echo ============================================================
type "%CLIENT_LOG%"
echo.
echo The same report is saved as client_crash.log in this folder.
echo Send that file or a screenshot of the final traceback for repair.
echo.
pause
exit /b %CLIENT_RC%
