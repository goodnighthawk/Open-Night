@echo off
setlocal EnableExtensions

title Open Night - Map Lab Ready Watch

set "REPO="
set "REPO_FILE=%LOCALAPPDATA%\OpenNight\map_lab_repo.txt"

rem Prefer the repository beside this BAT when it is already in the repo root.
if exist "%~dp0tools\map_lab_ready_watch.py" set "REPO=%~dp0"

rem Otherwise reuse the last repository location selected by the user.
if not defined REPO if exist "%REPO_FILE%" (
    set /p REPO=<"%REPO_FILE%"
)

rem Try common GitHub Desktop clone locations.
if not defined REPO if exist "%USERPROFILE%\Documents\GitHub\Open-Night\tools\map_lab_ready_watch.py" set "REPO=%USERPROFILE%\Documents\GitHub\Open-Night"
if not defined REPO if exist "%USERPROFILE%\GitHub\Open-Night\tools\map_lab_ready_watch.py" set "REPO=%USERPROFILE%\GitHub\Open-Night"
if not defined REPO if exist "%USERPROFILE%\OneDrive\Documents\GitHub\Open-Night\tools\map_lab_ready_watch.py" set "REPO=%USERPROFILE%\OneDrive\Documents\GitHub\Open-Night"
if not defined REPO if exist "%USERPROFILE%\Desktop\Open-Night\tools\map_lab_ready_watch.py" set "REPO=%USERPROFILE%\Desktop\Open-Night"

rem Validate any saved/discovered location. If it is stale, ask again.
if defined REPO if not exist "%REPO%\tools\map_lab_ready_watch.py" set "REPO="

if not defined REPO (
    echo.
    echo [Map Lab Watch] I could not automatically find your Open-Night clone.
    echo [Map Lab Watch] In GitHub Desktop use Repository ^> Show in Explorer, then copy that folder path.
    echo.
    set /p "REPO=Paste the full Open-Night repository folder here: "
    set "REPO=%REPO:"=%"
)

if not exist "%REPO%\tools\map_lab_ready_watch.py" goto :repo_error

if not exist "%LOCALAPPDATA%\OpenNight" mkdir "%LOCALAPPDATA%\OpenNight" >nul 2>&1
>"%REPO_FILE%" echo %REPO%

pushd "%REPO%" || goto :repo_error

echo [Map Lab Watch] Repository: %CD%

set "PY=py -3"
%PY% -c "import sys" >nul 2>&1
if errorlevel 1 set "PY=python"

%PY% -c "import pygame" >nul 2>&1
if errorlevel 1 (
    echo [Map Lab Watch] pygame-ce is missing - installing it once...
    %PY% -m pip install --user pygame-ce==2.5.8
    if errorlevel 1 goto :error
)

echo [Map Lab Watch] Checking dedicated alert playback device...
echo [Map Lab Watch] On first run, choose the monitor/HDMI/DisplayPort or motherboard output you want.
%PY% tools\map_lab_ready_watch.py --test-beep
if errorlevel 1 goto :error

echo.
echo [Map Lab Watch] Starting watcher...
echo [Map Lab Watch] Leave this window open.
echo [Map Lab Watch] Small progress will appear here as new commits arrive.
echo [Map Lab Watch] TRIPLE BEEP = new Map Lab version is ready to inspect.
echo [Map Lab Watch] Headphones can remain Windows default; the saved alert device is used directly.
echo.
%PY% tools\map_lab_ready_watch.py
if errorlevel 1 goto :error

popd
exit /b 0

:repo_error
echo.
echo [Map Lab Watch] Could not find tools\map_lab_ready_watch.py in:
echo   %REPO%
echo.
echo Delete "%REPO_FILE%" if you want to choose the repository folder again.
pause
exit /b 1

:error
echo.
echo [Map Lab Watch] Could not start. Read the error above.
popd
pause
exit /b 1
