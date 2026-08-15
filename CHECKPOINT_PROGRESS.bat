@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Open Night - Save GitHub Checkpoint

where git >nul 2>nul || goto :missing_git
call TEST_FAST.bat || exit /b 1

for /f "delims=" %%B in ('git branch --show-current') do set "BRANCH=%%B"
if not defined BRANCH goto :detached

git status --short
echo.
set /p "MESSAGE=Checkpoint description: "
if not defined MESSAGE goto :missing_message

echo.
echo This will commit all current Open Night changes to:
echo   !BRANCH!
set /p "CONFIRM=Type YES to commit and push: "
if /i not "!CONFIRM!"=="YES" (
  echo Cancelled. No files were committed.
  exit /b 0
)

git add -A || goto :fail
git diff --cached --quiet && goto :nothing
git commit -m "!MESSAGE!" || goto :fail
git push -u origin "!BRANCH!" || goto :push_failed

echo.
echo [OK] Progress is committed and pushed to GitHub.
exit /b 0

:nothing
echo Nothing changed; no checkpoint was needed.
exit /b 0
:missing_git
echo [ERROR] Git is not installed or is not on PATH.
goto :stop
:detached
echo [ERROR] Git is not currently on a named branch.
goto :stop
:missing_message
echo [ERROR] A checkpoint description is required.
goto :stop
:push_failed
echo [ERROR] The commit was saved locally, but GitHub push failed.
echo Open GitHub Desktop and click Push origin.
goto :stop
:fail
echo [ERROR] Git could not create the checkpoint.
:stop
pause
exit /b 1
