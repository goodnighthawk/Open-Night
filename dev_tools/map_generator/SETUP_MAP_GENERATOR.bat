@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating local Python environment...
  py -3 -m venv .venv 2>nul || python -m venv .venv || exit /b 1
)
".venv\Scripts\python.exe" -c "import PIL,pygame" >nul 2>&1
if errorlevel 1 (
  echo [setup] Installing primary Open Night generator dependencies: Pillow + pygame...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || exit /b 1
)
if /I not "%1"=="--quiet" echo [setup] Ready. Reference-image generator ready; no live map-service dependencies are installed.
exit /b 0
