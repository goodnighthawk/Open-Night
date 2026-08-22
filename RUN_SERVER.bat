@echo off
cd /d "%~dp0"
title OPEN NIGHT v2.0 - Grid Server
if not exist .venv\Scripts\python.exe call START_HERE.bat --setup-only
.venv\Scripts\python.exe v100_server.py
