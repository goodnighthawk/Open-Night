@echo off
setlocal
cd /d "%~dp0"
title Open Night v4.0 - GWB Playtest
if not exist ".venv\Scripts\python.exe" (
  call START_HERE.bat --setup-only
  if errorlevel 1 exit /b 1
)
call QUICK_LOCAL_TEST.bat
exit /b %ERRORLEVEL%
