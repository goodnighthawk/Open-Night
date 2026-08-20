@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OPEN NIGHT v1.1 - Update Internet Server

call :main
set "DEPLOY_RC=%ERRORLEVEL%"

echo.
if "%DEPLOY_RC%"=="0" (
  echo Press any key to close this window.
) else (
  echo ============================================================
  echo [STOPPED] Deployment did not complete. Exit code %DEPLOY_RC%.
  echo The window has been kept open so the error remains visible.
  echo ============================================================
)
pause >nul
exit /b %DEPLOY_RC%

:main
echo ============================================================
echo   OPEN NIGHT v1.1 // RAILWAY SERVER UPDATE
echo ============================================================
echo.

where railway.cmd >nul 2>&1
if errorlevel 1 goto :missing_railway

rem Railway is installed by npm as railway.cmd. CALL is required when one
rem batch/CMD script invokes another or Windows will not return control here.
call railway.cmd status >nul 2>&1
if errorlevel 1 goto :link_project
goto :deploy

:link_project
echo This new folder is not yet linked to Railway.
echo When asked, select your EXISTING open-night project and service.
echo Do not create a second project.
echo.
call railway.cmd link
if errorlevel 1 goto :link_failed

:deploy
echo.
echo Uploading the current Open Night v1.1 folder to Railway...
echo This updates the existing internet server and keeps its public domain.
echo v1.1 preserves existing prototype MySQL data and bug reports during deployment.
echo.
pause
call railway.cmd up
if errorlevel 1 goto :deploy_failed

echo.
echo ============================================================
echo   OPEN NIGHT v1.1 SERVER UPDATE COMPLETE
echo ============================================================
echo The configured desktop client automatically detects:
echo.
echo   wss://open-night-production.up.railway.app
echo.
echo The launcher should report server version v1.1 after Railway finishes restarting.
exit /b 0

:missing_railway
echo [NOT READY] railway.cmd was not found.
echo Reopen PowerShell after installing it, or reinstall with:
echo   npm.cmd install -g @railway/cli
exit /b 10

:link_failed
echo.
echo [FAILED] This folder was not linked to the existing open-night project.
echo Run this file again and select the existing project and service.
exit /b 20

:deploy_failed
echo.
echo [FAILED] Railway did not finish the update.
echo Read the error above. You can also run railway.cmd logs.
exit /b 30
