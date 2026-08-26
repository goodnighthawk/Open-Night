@echo off
setlocal
cd /d "%~dp0"
python dev_tools\map_generator\tools\build_v4_approved_sprite_layout.py
if errorlevel 1 (
  echo.
  echo Approved v4 sprite layout build failed. Review the error above.
  pause
  exit /b 1
)
echo.
echo Approved v4 sprite layout built successfully.
pause
