@echo off
setlocal
cd /d "%~dp0"
title Open Night v4 - 64 Player City Load Test

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo Running the isolated 64-player city-wide v4 load proof...
"%PY%" -u tools\v4_city_load_test.py %*
exit /b %ERRORLEVEL%
