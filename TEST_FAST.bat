@echo off
setlocal
cd /d "%~dp0"
title Open Night - Fast Checks

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo [1/6] Compile smoke...
"%PY%" -m compileall -q client.py server.py database.py environment_art.py gameplay tools dev_tools\map_generator || goto :fail
echo [2/6] Multiplayer movement...
"%PY%" tools\multiplayer_movement_audit.py || goto :fail
echo [3/6] Map validation...
"%PY%" tools\validate_mapfiles.py || goto :fail
echo [4/6] Art rules...
"%PY%" tools\art_rule_audit.py || goto :fail
echo [5/6] Railway deployment rules...
"%PY%" tools\railway_batch_audit.py || goto :fail
echo [6/6] Moderated bug report queue...
"%PY%" tools\bug_moderation_audit.py || goto :fail

echo.
echo FAST CHECKS PASSED.
exit /b 0

:fail
echo.
echo [ERROR] Fast checks failed. Nothing was checkpointed.
pause
exit /b 1
