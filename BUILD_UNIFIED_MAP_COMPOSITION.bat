@echo off
setlocal
cd /d "%~dp0"
python dev_tools\map_generator\tools\build_v090_release_candidate.py --clean
if errorlevel 1 (
  echo.
  echo v0.9.0 release-candidate map build failed. Review the error above.
  pause
  exit /b 1
)
echo.
echo v0.9.0 release-candidate map composition completed successfully.
echo Review the generated day/night composition before promotion.
pause
