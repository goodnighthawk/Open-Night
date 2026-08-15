@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set /p GAMEVER=<VERSION.txt
title Python MMO %GAMEVER%
rem OPEN NIGHT branch note: START_OPEN_NIGHT.bat is the preferred launcher-first entry point.

set "PYEXE="
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
if not defined PYEXE (
  where python >nul 2>&1
  if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE (
  echo Python not found. Installing Python 3.12 for the current user...
  where winget >nul 2>&1 || goto :no_python
  winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
  if errorlevel 1 goto :failed
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe") else (set "PYEXE=python")
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating local virtual environment...
  "%PYEXE%" -m venv .venv || goto :failed
)
set "PYEXE=.venv\Scripts\python.exe"
echo [2/3] Installing/updating game prerequisites...
"%PYEXE%" -m pip install --disable-pip-version-check -r requirements.txt || goto :failed
echo [3/3] Preparing portable shared assets/settings...
"%PYEXE%" bootstrap.py || goto :failed
if /I "%~1"=="--setup-only" exit /b 0

:menu
cls
echo ============================================================
echo      PYTHON MMO %GAMEVER% — USER ASSETS / 3X RUN BUILD
echo ============================================================
echo Shared assets/config survive version upgrades automatically.
echo Art review renders do NOT require a running server.
echo.
echo  1   Quick local test ^(memory DB; server + client^)
echo  2   Server Control ^(persistent MySQL^)
echo  3   Client launcher
echo  4   Validate Map 001 + art placement rules
echo  5   Build/refresh 32px A1 logical grid cache
echo  6   Show/export A1 chunk reference
echo  7   Render approved-art review PNGs
echo  8   Watch art/map files and auto-render reviews
echo  9   Export art-rule audit CSV
echo  10  Run headless bot stress test
echo  11  Run browser client ^(pygbag^)
echo  12  Open portable shared-data folder
echo  13  Build next-version issue fix list
echo  0   Exit
echo.
set /p CHOICE=Select: 
if "%CHOICE%"=="1" goto :quick
if "%CHOICE%"=="2" goto :servercontrol
if "%CHOICE%"=="3" goto :client
if "%CHOICE%"=="4" goto :validate
if "%CHOICE%"=="5" goto :gridbuild
if "%CHOICE%"=="6" goto :chunkref
if "%CHOICE%"=="7" goto :artreview
if "%CHOICE%"=="8" goto :artwatch
if "%CHOICE%"=="9" goto :artaudit
if "%CHOICE%"=="10" goto :stress
if "%CHOICE%"=="11" goto :web
if "%CHOICE%"=="12" goto :shared
if "%CHOICE%"=="13" goto :issuefix
if "%CHOICE%"=="0" exit /b 0
goto :menu

:quick
call QUICK_LOCAL_TEST.bat
goto :menu

:servercontrol
start "PYMMO SERVER CONTROL" "%CD%\.venv\Scripts\python.exe" server_launcher.py
goto :menu
:client
start "PYMMO CLIENT" "%CD%\.venv\Scripts\python.exe" client.py
goto :menu
:validate
"%PYEXE%" tools\validate_mapfiles.py
pause
goto :menu
:gridbuild
"%PYEXE%" tools\build_grid_map.py --map map_001_gwb_corridor
pause
goto :menu
:chunkref
"%PYEXE%" tools\chunk_reference.py
pause
goto :menu
:artreview
set PYMMO_ART_REVIEW_LOCAL=1
"%PYEXE%" tools\art_review.py
pause
goto :menu
:artwatch
set PYMMO_ART_REVIEW_LOCAL=1
"%PYEXE%" tools\art_review.py --watch
pause
goto :menu
:artaudit
"%PYEXE%" tools\art_rule_audit.py
pause
goto :menu
:stress
"%PYEXE%" tools\stress_test_bots.py
pause
goto :menu
:web
call RUN_WEB_CLIENT.bat
goto :menu
:shared
for /f "usebackq delims=" %%I in (`"%PYEXE%" -c "from portable_paths import shared_root; print(shared_root())"`) do set "SHARED=%%I"
explorer "%SHARED%"
goto :menu
:issuefix
"%PYEXE%" tools\issue_fixlist.py
pause
goto :menu
:no_python
echo [ERROR] Python and winget are unavailable. Install Python 3.12+ and rerun START_HERE.bat.
pause
exit /b 1
:failed
echo [ERROR] Setup failed. Review the message above.
pause
exit /b 1
