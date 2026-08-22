@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OPEN NIGHT v2.3 - Grid Client

if not exist ".venv\Scripts\python.exe" (
  echo Preparing the Open Night Python environment...
  call START_HERE.bat --setup-only
)

".venv\Scripts\python.exe" -c "import imageio_ffmpeg" >nul 2>&1
if errorlevel 1 (
  echo Updating audio playback support...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Could not install the live-radio decoder.
    pause
    exit /b 3
  )
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

echo Open Night v2.3 GridWorld-authoritative desktop client starting...
echo Ground, minimap, and M map use GridWorld; legacy place names may remain as labels only.
echo Discovered multiplayer servers must advertise the same v2.2 wire version before JOIN.
echo Crash log: %CLIENT_LOG%
echo.

".venv\Scripts\python.exe" -u v100_client.py >"%CLIENT_LOG%" 2>&1
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
