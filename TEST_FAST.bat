@echo off
setlocal
cd /d "%~dp0"
title Open Night - Fast Checks

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo [1/10] Compile smoke...
"%PY%" -m compileall -q client.py server.py database.py environment_art.py gameplay tools dev_tools\map_generator || goto :fail
echo [2/10] Multiplayer movement...
"%PY%" tools\multiplayer_movement_audit.py || goto :fail
echo [3/10] Map validation...
"%PY%" tools\validate_mapfiles.py || goto :fail
echo [4/10] Art rules...
"%PY%" tools\art_rule_audit.py || goto :fail
echo [5/10] Railway deployment rules...
"%PY%" tools\railway_batch_audit.py || goto :fail
echo [6/10] Moderated bug report queue...
"%PY%" tools\bug_moderation_audit.py || goto :fail
echo [7/10] Multiplayer reliability...
"%PY%" tools\v074_reliability_audit.py || goto :fail
echo [8/10] Clipboard and chat hints...
"%PY%" tools\v075_clipboard_chat_audit.py || goto :fail
echo [9/10] Pass 19 building-art convergence...
"%PY%" tools\building_art_convergence_audit.py --strict || goto :fail
echo [10/10] Pass 19 promoted map/package...
"%PY%" tools\pass19_map_audit.py || goto :fail

echo.
echo FAST CHECKS PASSED.
exit /b 0

:fail
echo.
echo [ERROR] Fast checks failed. Nothing was checkpointed.
pause
exit /b 1
