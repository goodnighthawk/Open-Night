@echo off
setlocal
cd /d "%~dp0dev_tools\map_generator"
call SETUP_MAP_GENERATOR.bat --quiet || exit /b 1
"%~dp0dev_tools\map_generator\.venv\Scripts\python.exe" map_generator.py reference-studio
