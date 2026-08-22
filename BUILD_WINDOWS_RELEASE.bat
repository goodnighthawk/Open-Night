@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OPEN NIGHT - Windows Release Builder

where ISCC.exe >nul 2>&1
if errorlevel 1 (
  if not exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" if not exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" (
    echo [ERROR] Inno Setup 6 is required to create the installer.
    echo Install it with: winget install JRSoftware.InnoSetup
    pause
    exit /b 2
  )
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\windows\build_release.ps1" %*
set "BUILD_RC=%ERRORLEVEL%"
if not "%BUILD_RC%"=="0" (
  echo.
  echo [ERROR] Windows release build failed with exit code %BUILD_RC%.
  pause
)
exit /b %BUILD_RC%
