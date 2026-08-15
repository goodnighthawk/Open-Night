@echo off
setlocal
cd /d "%~dp0"
python dev_tools\map_generator\tools\build_unified_composition.py --clean
if errorlevel 1 (
  echo.
  echo Unified map composition failed. Review the error above.
  pause
  exit /b 1
)
echo.
echo Unified map composition completed successfully.
pause
