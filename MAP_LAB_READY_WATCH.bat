@echo off
setlocal
cd /d "%~dp0"
title Open Night - Map Lab Ready Watch

set "PY=py -3"
%PY% -c "import sys" >nul 2>&1
if errorlevel 1 set "PY=python"

%PY% -c "import pygame" >nul 2>&1
if errorlevel 1 (
    echo [Map Lab Watch] pygame-ce is missing - installing it once...
    %PY% -m pip install --user pygame-ce==2.5.8
    if errorlevel 1 goto :error
)

echo [Map Lab Watch] Testing Windows default playback device...
%PY% tools\map_lab_ready_watch.py --test-beep

echo.
echo [Map Lab Watch] Starting watcher...
echo [Map Lab Watch] Leave this window open.
echo [Map Lab Watch] TRIPLE SYSTEM BEEP = new Map Lab version is ready to inspect.
echo [Map Lab Watch] The alert follows your Windows default playback device.
echo.
%PY% tools\map_lab_ready_watch.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo [Map Lab Watch] Could not start. Read the error above.
pause
exit /b 1
