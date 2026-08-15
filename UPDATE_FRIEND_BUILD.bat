@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title OPEN NIGHT - Friend Build Updater

echo ============================================================
echo   OPEN NIGHT // FRIEND BUILD UPDATER
echo ============================================================
echo This updates an extracted friend copy without deleting saves,
echo friends.csv, the Python environment, logs, or other local files.
echo.

if exist ".git\" (
  echo [INFO] This is a Git clone. Using the safe main-branch updater...
  call UPDATE_OPEN_NIGHT.bat
  echo.
  echo Update check finished.
  pause
  exit /b %ERRORLEVEL%
)

set "UPDATE_ROOT=%TEMP%\open-night-friend-update-%RANDOM%-%RANDOM%"
set "ZIP_FILE=%UPDATE_ROOT%\Open-Night-update.zip"
set "EXTRACT_DIR=%UPDATE_ROOT%\expanded"
mkdir "%UPDATE_ROOT%" >nul 2>nul
mkdir "%EXTRACT_DIR%" >nul 2>nul

if not "%~1"=="" (
  set "IMPORT_ZIP=%~f1"
  goto :import_zip
)

echo  1  Download the newest GitHub main build
echo  2  Import an Open Night ZIP already on this computer
echo  0  Cancel
echo.
set /p UPDATE_CHOICE=Select:
if "%UPDATE_CHOICE%"=="0" goto :cancel
if "%UPDATE_CHOICE%"=="1" goto :download
if "%UPDATE_CHOICE%"=="2" goto :choose_zip
echo Invalid selection.
goto :fail

:download
echo [1/4] Downloading github.com/goodnighthawk/Open-Night main...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/goodnighthawk/Open-Night/archive/refs/heads/main.zip' -OutFile '%ZIP_FILE%'"
if errorlevel 1 goto :download_fail
set "IMPORT_ZIP=%ZIP_FILE%"
goto :import_zip

:choose_zip
echo.
echo Drag an Open Night .zip file into this window, then press Enter.
set /p IMPORT_ZIP=ZIP path:
set "IMPORT_ZIP=%IMPORT_ZIP:"=%"

:import_zip
if not exist "%IMPORT_ZIP%" (
  echo [ERROR] ZIP not found: %IMPORT_ZIP%
  goto :fail
)
echo [2/4] Expanding update...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -LiteralPath '%IMPORT_ZIP%' -DestinationPath '%EXTRACT_DIR%' -Force"
if errorlevel 1 goto :bad_zip

set "SOURCE_DIR="
for /f "delims=" %%V in ('dir /b /s "%EXTRACT_DIR%\VERSION.txt" 2^>nul') do if not defined SOURCE_DIR set "SOURCE_DIR=%%~dpV"
if not defined SOURCE_DIR goto :bad_zip
if not exist "!SOURCE_DIR!client.py" goto :bad_zip
if not exist "!SOURCE_DIR!START_OPEN_NIGHT.bat" goto :bad_zip
if not exist "!SOURCE_DIR!versioning.py" goto :bad_zip

for /f "usebackq delims=" %%V in ("!SOURCE_DIR!VERSION.txt") do if not defined NEW_VERSION set "NEW_VERSION=%%V"
echo [3/4] Installing !NEW_VERSION!...
robocopy "!SOURCE_DIR!" "%CD%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP ^
  /XD ".git" ".venv" "__pycache__" "build" "web-cache" ^
  /XF "friends.csv" "client_crash.log" "server_crash.log" >nul
set "ROBOCOPY_CODE=!ERRORLEVEL!"
if !ROBOCOPY_CODE! GEQ 8 goto :copy_fail

echo [4/4] Refreshing Python prerequisites and portable files...
call START_HERE.bat --setup-only
if errorlevel 1 goto :setup_fail

echo.
echo ============================================================
echo   UPDATE COMPLETE: !NEW_VERSION!
echo ============================================================
echo Run START_OPEN_NIGHT.bat to play. The matching-version gate
echo will prevent an old client from joining a newer server.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath '%UPDATE_ROOT%' -Recurse -Force -ErrorAction SilentlyContinue" >nul 2>nul
pause
exit /b 0

:download_fail
echo [ERROR] GitHub download failed. Check the internet connection, or choose option 2 with a shared ZIP.
goto :fail
:bad_zip
echo [ERROR] This is not a complete Open Night update ZIP.
goto :fail
:copy_fail
echo [ERROR] Windows could not copy the update files. Close the game/server and retry.
goto :fail
:setup_fail
echo [ERROR] Files updated, but prerequisite setup failed. Run START_HERE.bat again.
goto :fail
:cancel
echo Update cancelled; no game files were changed.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath '%UPDATE_ROOT%' -Recurse -Force -ErrorAction SilentlyContinue" >nul 2>nul
exit /b 0
:fail
echo.
echo Nothing else will be changed. This window stays open so the error can be read.
pause
exit /b 1
