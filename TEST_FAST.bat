@echo off
setlocal
cd /d "%~dp0"
title Open Night - Fast Checks

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo [1/5] Compile smoke...
"%PY%" -m compileall -q client.py server.py database.py environment_art.py gameplay tools dev_tools\map_generator || goto :fail
echo [2/5] Multiplayer movement...
"%PY%" tools\multiplayer_movement_audit.py || goto :fail
echo [3/5] Map validation...
"%PY%" tools\validate_mapfiles.py || goto :fail
echo [4/5] Art rules...
"%PY%" tools\art_rule_audit.py || goto :fail
echo [5/5] Railway deployment rules...
"%PY%" tools\railway_batch_audit.py || goto :fail

echo.
echo FAST CHECKS PASSED.
exit /b 0

:fail
echo.
echo [ERROR] Fast checks failed. Nothing was checkpointed.
pause
exit /b 1
