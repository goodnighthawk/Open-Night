@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call START_HERE.bat --setup-only
".venv\Scripts\python.exe" dev_tools\character_preview\sprite_tester.py "%~dp0assets\characters\master_dual_camera"
