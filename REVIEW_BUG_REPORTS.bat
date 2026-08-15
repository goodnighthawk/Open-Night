@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Open Night - Human Bug Report Review

echo ============================================================
echo   OPEN NIGHT // HUMAN BUG REPORT REVIEW
echo ============================================================
echo Player reports are untrusted and remain PENDING until you
echo explicitly approve or reject each report here.
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Preparing the Open Night Python environment...
  call START_HERE.bat --setup-only
  if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -u tools\review_bug_reports.py
set "REVIEW_RC=%ERRORLEVEL%"
echo.
if not "%REVIEW_RC%"=="0" (
  echo [STOPPED] Review tool exited with code %REVIEW_RC%.
  echo Check the server is online and that the token exactly matches
  echo Railway variable PYMMO_BUG_ADMIN_TOKEN.
)
echo Press any key to close.
pause >nul
exit /b %REVIEW_RC%

:failed
echo [ERROR] Python environment setup failed.
pause
exit /b 1
