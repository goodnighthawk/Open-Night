@echo off
setlocal
cd /d "%~dp0"
title Open Night - Quick Local Test

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Local Python environment was not found.
  echo Run START_HERE.bat once first to create it.
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo   OPEN NIGHT - QUICK LOCAL TEST
echo ============================================================
echo Any Python failure will be printed here.
echo Server/client child consoles stay open if they crash.
echo.

".venv\Scripts\python.exe" -u tools\quick_local_test.py
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo ============================================================
  echo [ERROR] QUICK LOCAL TEST FAILED - exit code %RC%
  echo Read the Python error/traceback above.
  echo If SERVER or CLIENT failed, its separate console is also
  echo intentionally being kept open for inspection.
  echo ============================================================
  echo.
  pause
  exit /b %RC%
)

echo.
echo [OK] Quick Local Test launcher completed successfully.
exit /b 0
