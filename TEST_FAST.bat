@echo off
setlocal
cd /d "%~dp0"
title Open Night - Fast Checks

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo [1/11] Compile smoke...
"%PY%" -m compileall -q client.py server.py game_modes.py database.py environment_art.py gameplay tools dev_tools\map_generator || goto :fail
echo [2/11] v4 server mode/apartment privacy...
"%PY%" verify_v4_server_contract.py || goto :fail
echo [3/11] Multiplayer movement...
"%PY%" tools\multiplayer_movement_audit.py || goto :fail
echo [4/11] Map validation...
"%PY%" tools\validate_mapfiles.py || goto :fail
echo [5/11] Art rules...
"%PY%" tools\art_rule_audit.py || goto :fail
echo [6/11] Railway deployment rules...
"%PY%" tools\railway_batch_audit.py || goto :fail
echo [7/11] Moderated bug report queue...
"%PY%" tools\bug_moderation_audit.py || goto :fail
echo [8/11] Multiplayer reliability...
"%PY%" tools\v074_reliability_audit.py || goto :fail
echo [9/11] Clipboard and chat hints...
"%PY%" tools\v075_clipboard_chat_audit.py || goto :fail
echo [10/11] Pass 19 building-art convergence...
"%PY%" tools\building_art_convergence_audit.py --strict || goto :fail
echo [11/11] Canonical release authority...
"%PY%" tools\audit_main_release.py || goto :fail

echo.
echo FAST CHECKS PASSED.
exit /b 0

:fail
echo.
echo [ERROR] Fast checks failed. Nothing was checkpointed.
pause
exit /b 1
