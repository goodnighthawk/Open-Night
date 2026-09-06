@echo off
setlocal
cd /d "%~dp0"
title Open Night v4 - Gameplay Checks

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo [1/6] Interiors, chat, SMS, and trading...
"%PY%" tools\multiplayer_interior_social_audit.py || goto :fail
echo [2/6] Vehicle driver and passenger seats...
"%PY%" tools\vehicle_passenger_audit.py || goto :fail
echo [3/6] Vehicle collisions and pedestrian impacts...
"%PY%" tools\vehicle_body_runover_audit.py || goto :fail
echo [4/6] On-foot prediction and reconciliation...
"%PY%" tools\v4_prediction_audit.py || goto :fail
echo [5/6] Server-authoritative vehicle smoothing...
"%PY%" tools\v4_vehicle_authority_audit.py || goto :fail
echo [6/6] Desktop runtime startup and HUD interactions...
"%PY%" tools\audit_hud_v3_runtime.py || goto :fail

echo.
echo V4 GAMEPLAY CHECKS PASSED. Live controls, HUD, and latency-feel checks remain separate.
exit /b 0

:fail
echo.
echo V4 GAMEPLAY CHECKS FAILED. Review the error above.
exit /b 1
