@echo off
setlocal
cd /d "%~dp0"
title Open Night - Full Release Verification

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo [1/3] Installing the current semantic reference map...
"%PY%" dev_tools\map_generator\tools\compile_reference_map.py --install || goto :fail
echo [2/3] Rendering all approved day/night review views...
"%PY%" dev_tools\map_generator\tools\render_callback_preview.py --mode both || goto :fail
echo [3/3] Running complete local QA...
call LOCAL_QA.bat || goto :fail

echo.
echo RELEASE VERIFICATION PASSED.
exit /b 0

:fail
echo.
echo [ERROR] Release verification failed. Review the message above.
pause
exit /b 1
