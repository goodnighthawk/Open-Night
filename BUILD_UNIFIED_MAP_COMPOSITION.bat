@echo off
setlocal
cd /d "%~dp0"
python dev_tools\map_generator\tools\build_pass19_art_convergence.py --clean
if errorlevel 1 (
  echo.
  echo Pass 19 unified map composition failed. Review the error above.
  pause
  exit /b 1
)
echo.
echo Pass 19 unified map composition completed successfully.
echo Review the generated day/night composition before promotion.
pause
