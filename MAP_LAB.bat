@echo off
setlocal
cd /d "%~dp0"
title Open Night - Map Lab

set "PY=py -3"
%PY% -c "import sys" >nul 2>&1
if errorlevel 1 set "PY=python"

%PY% -c "import pygame" >nul 2>&1
if errorlevel 1 (
    echo [Map Lab] pygame-ce is missing - installing it once...
    %PY% -m pip install --user pygame-ce==2.5.8
    if errorlevel 1 goto :error
)

rem Proof axis convention used for every Map Lab render:
rem North = screen up, East = right, South = down, West = left.
rem Therefore +x = East and +y = South.
set "OPEN_NIGHT_PROOF_COMPASS=1"

echo [Map Lab] Starting local Ground + Roof visual iteration loop...
echo [Map Lab] AXES: N=up E=right S=down W=left; +x=E +y=S
%PY% tools\map_lab.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo [Map Lab] Could not start. Read the error above.
pause
exit /b 1
