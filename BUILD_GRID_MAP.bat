@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYEXE=python"
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
"%PYEXE%" tools\build_grid_map.py --map map_001_gwb_corridor
if errorlevel 1 (
  echo.
  echo Grid build failed.
  pause
  exit /b 1
)
echo.
echo Grid map cache is current. A1 labels are in mapfiles\compiled\map_001_gwb_corridor\chunk_index.csv
pause
