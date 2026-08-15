@echo off
setlocal
cd /d "%~dp0"
set "OPEN_NIGHT_GAME_ROOT=%~dp0"
call dev_tools\map_generator\MAP_GENERATOR.bat
