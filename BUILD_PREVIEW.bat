@echo off
setlocal
cd /d "%~dp0"
title Open Night - Fast Map Preview

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo Building the Fort Lee night crop only...
"%PY%" dev_tools\map_generator\tools\render_callback_preview.py --view fortlee --mode night
if errorlevel 1 goto :fail

echo.
echo Preview ready:
echo dev_tools\map_generator\output\fortlee_callback_night.png
exit /b 0

:fail
echo.
echo [ERROR] Preview build failed. Review the message above.
pause
exit /b 1
