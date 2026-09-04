@echo off
setlocal
cd /d "%~dp0"
title Open Night v4 - Multiplayer Session Test

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo Running the isolated v4 two-player visibility, reconnect, and version audit...
"%PY%" -u tools\multiplayer_map_roster_audit.py %*
exit /b %ERRORLEVEL%
