@echo off
setlocal
cd /d "%~dp0"
title Open Night v4 - 15 Player Housing Test

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo Running the isolated 14-apartment plus one-overflow housing audit...
"%PY%" -u tools\v4_housing_network_audit.py %*
exit /b %ERRORLEVEL%
