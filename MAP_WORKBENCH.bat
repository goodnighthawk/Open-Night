@echo off
setlocal
cd /d "%~dp0"
title Open Night - Standalone Map Workbench

set "PY=py -3"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

%PY% -c "import pygame" >nul 2>&1
if errorlevel 1 (
    echo [Map Workbench] pygame-ce is missing - installing it once...
    %PY% -m pip install --user pygame-ce==2.5.8
    if errorlevel 1 goto :error
)

%PY% map_workbench.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo [Map Workbench] Could not start. Read the error above.
pause
exit /b 1
