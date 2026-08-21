@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OPEN NIGHT - Launcher

call UPDATE_OPEN_NIGHT.bat --launcher

if not exist ".venv\Scripts\python.exe" (
  echo ============================================================
  echo   OPEN NIGHT // first-run setup
  echo ============================================================
  echo Preparing the existing Python MMO v2.5 environment first...
  call START_HERE.bat --setup-only
  if errorlevel 1 goto :fail
)

".venv\Scripts\python.exe" open_night_player_launcher.py
exit /b %ERRORLEVEL%

:fail
echo.
echo [ERROR] OPEN NIGHT setup failed. Review the message above.
pause
exit /b 1
