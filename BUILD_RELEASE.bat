@echo off
setlocal
cd /d "%~dp0"
title Open Night - Full Release Verification

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo [1/4] Building the current GWB map and its five playable layers...
"%PY%" dev_tools\map_generator\tools\build_v4_approved_sprite_layout.py || goto :fail
"%PY%" tools\promote_gwb_workbench_to_v4.py || goto :fail
echo [2/4] Checking map geometry, transitions, and source artwork...
"%PY%" tools\v4_map_workbench_audit.py || goto :fail
"%PY%" tools\audit_v4_gwb_runtime_promotion.py || goto :fail
echo [3/4] Checking movement and the multiplayer contract...
"%PY%" verify_v4_server_contract.py || goto :fail
"%PY%" tools\v4_prediction_audit.py || goto :fail
"%PY%" tools\multiplayer_map_roster_audit.py || goto :fail
echo [4/4] Packaging the map workbench...
"%PY%" tools\package_gwb_map_previewer.py || goto :fail

echo.
echo V4.0 PLAYTEST VERIFICATION PASSED. Production deployment is separate.
exit /b 0

:fail
echo.
echo [ERROR] Release verification failed. Review the message above.
pause
exit /b 1
