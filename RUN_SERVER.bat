@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call START_HERE.bat --setup-only
.venv\Scripts\python.exe v100_server.py
