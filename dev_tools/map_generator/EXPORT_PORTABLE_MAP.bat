@echo off
setlocal
cd /d "%~dp0"
call SETUP_MAP_GENERATOR.bat --quiet || exit /b 1
set "OUT=%~dp0exports"
if not "%~1"=="" set "OUT=%~1"
"%~dp0.venv\Scripts\python.exe" map_generator.py export-map "%OUT%" --name Map_001_GWB
echo.
echo Move Map_001_GWB.map together with Map_001_GWB_assets\ to any folder.
pause
