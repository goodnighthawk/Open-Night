@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OPEN NIGHT - Synchronize and Build Windows Release

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\windows\sync_and_build.ps1" %*
set "SYNC_RC=%ERRORLEVEL%"
if not "%SYNC_RC%"=="0" (
  echo.
  echo [ERROR] Synchronization or release build failed with exit code %SYNC_RC%.
  pause
)
exit /b %SYNC_RC%
