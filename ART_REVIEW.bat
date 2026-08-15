@echo off
setlocal
cd /d "%~dp0"
set PYMMO_ART_REVIEW_LOCAL=1
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\art_review.py
) else (
  python tools\art_review.py
)
if errorlevel 1 pause
endlocal
