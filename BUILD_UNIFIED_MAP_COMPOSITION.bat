@echo off
setlocal
cd /d "%~dp0"
python dev_tools\map_generator\tools\build_pass19b_frontage_release_candidate.py --clean
if errorlevel 1 (
  echo.
  echo Pass 19b unified map composition failed. Review the error above.
  pause
  exit /b 1
)
echo.
echo Pass 19b unified map composition completed successfully.
echo Review the generated day/night composition before v0.9.0 promotion.
pause
