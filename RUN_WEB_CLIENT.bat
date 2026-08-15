@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" call START_HERE.bat --setup-only
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python environment was not created.
  pause
  exit /b 1
)

set "WEB_STAGE=%TEMP%\python_mmo_v22_web_%RANDOM%_%RANDOM%"
echo.
echo ==============================================================
echo   Open Night v0.7.3 - full Pygame browser client
echo ==============================================================
echo Preparing a clean browser build without the desktop .venv...

set "PYGBAG_VERSION="
for /f "tokens=2" %%V in ('".venv\Scripts\python.exe" -m pip show pygbag 2^>nul ^| findstr /b /c:"Version:"') do set "PYGBAG_VERSION=%%V"
if not "%PYGBAG_VERSION%"=="0.9.2" (
  echo Correcting Pygbag to 0.9.2 to avoid the 0.9.3 grey-screen loader bug...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet "pygbag==0.9.2"
  if errorlevel 1 goto :fail
)

".venv\Scripts\python.exe" tools\prepare_web_stage.py "%WEB_STAGE%"
if errorlevel 1 goto :fail

echo.
echo Building and serving at http://localhost:8000/
echo The browser game automatically connects to the configured Railway server:
echo   wss://open-night-production.up.railway.app
echo Use ?server=host:port in the browser URL only to override it.
echo.
".venv\Scripts\python.exe" -m pygbag --app_name open-night --package open-night-v0-7-3 --title "Open Night v0.7.3" --version 0.9.2 --port 8000 --ume_block 0 --disable-sound-format-error "%WEB_STAGE%"
set "RC=%ERRORLEVEL%"

if exist "%WEB_STAGE%" rmdir /s /q "%WEB_STAGE%" >nul 2>nul
if not "%RC%"=="0" goto :failcode
exit /b 0

:fail
set "RC=%ERRORLEVEL%"
if exist "%WEB_STAGE%" rmdir /s /q "%WEB_STAGE%" >nul 2>nul
:failcode
echo.
echo [ERROR] Web client exited with code %RC%.
pause
exit /b %RC%
