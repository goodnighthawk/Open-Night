@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Open Night - WIP Map Preview Channel

set "PREVIEW_DIR=%~dp0..\Open-Night-Map-Preview"
set "PREVIEW_BRANCH=map-preview-local"

set "GIT_EXE="
for /f "delims=" %%G in ('where git.exe 2^>nul') do if not defined GIT_EXE set "GIT_EXE=%%G"
if not defined GIT_EXE if defined LOCALAPPDATA (
  for /f "delims=" %%G in ('dir /b /s "%LOCALAPPDATA%\GitHubDesktop\app-*\resources\app\git\cmd\git.exe" 2^>nul') do set "GIT_EXE=%%G"
)
if not defined GIT_EXE goto :missing_git
if not exist ".git" goto :not_clone

echo ============================================================
echo   OPEN NIGHT // WORK IN PROGRESS MAP CHANNEL
echo ============================================================
echo Stable game:  %~dp0
echo Preview game: !PREVIEW_DIR!
echo.

echo [1/4] Reading the latest stable and preview branches...
"!GIT_EXE!" fetch origin main:refs/remotes/origin/main --quiet || goto :fetch_failed
"!GIT_EXE!" fetch origin map-preview:refs/remotes/origin/map-preview --quiet 2>nul
if errorlevel 1 (
  echo [SETUP] Creating the GitHub map-preview branch from current origin/main...
  "!GIT_EXE!" push origin refs/remotes/origin/main:refs/heads/map-preview || goto :create_failed
  "!GIT_EXE!" fetch origin map-preview:refs/remotes/origin/map-preview --quiet || goto :fetch_failed
)

echo [2/4] Preparing the separate preview installation...
if not exist "!PREVIEW_DIR!\.git" (
  if exist "!PREVIEW_DIR!" goto :preview_folder_conflict
  "!GIT_EXE!" show-ref --verify --quiet refs/heads/!PREVIEW_BRANCH!
  if errorlevel 1 (
    "!GIT_EXE!" worktree add -b !PREVIEW_BRANCH! "!PREVIEW_DIR!" origin/map-preview || goto :worktree_failed
  ) else (
    "!GIT_EXE!" worktree add "!PREVIEW_DIR!" !PREVIEW_BRANCH! || goto :worktree_failed
  )
)

echo [3/4] Applying the newest safe fast-forward preview update...
"!GIT_EXE!" -C "!PREVIEW_DIR!" diff --quiet -- || goto :dirty
"!GIT_EXE!" -C "!PREVIEW_DIR!" diff --cached --quiet -- || goto :dirty
"!GIT_EXE!" -C "!PREVIEW_DIR!" fetch origin map-preview:refs/remotes/origin/map-preview --quiet || goto :fetch_failed
"!GIT_EXE!" -C "!PREVIEW_DIR!" merge --ff-only origin/map-preview --quiet || goto :diverged

set "PREVIEW_SHA="
for /f "delims=" %%H in ('"!GIT_EXE!" -C "!PREVIEW_DIR!" rev-parse --short HEAD') do set "PREVIEW_SHA=%%H"
set "PREVIEW_SUBJECT="
for /f "delims=" %%S in ('"!GIT_EXE!" -C "!PREVIEW_DIR!" log -1 --pretty^=%%s') do set "PREVIEW_SUBJECT=%%S"

echo [4/4] Launching preview !PREVIEW_SHA!...
echo !PREVIEW_SUBJECT!
echo.
set "OPEN_NIGHT_SKIP_UPDATE=1"
set "OPEN_NIGHT_MAP_PREVIEW=map-preview !PREVIEW_SHA!"
set "PYMMO_SHARED_DATA=%LOCALAPPDATA%\OpenNightMapPreview\shared"
set "OPEN_NIGHT_FEEDBACK_ROOT=%LOCALAPPDATA%\OpenNightMapPreview\feedback"
call "!PREVIEW_DIR!\START_OPEN_NIGHT.bat"
exit /b %ERRORLEVEL%

:missing_git
echo [ERROR] Git for Windows was not found. Reopen Windows after installing Git.
goto :stop
:not_clone
echo [ERROR] Put this BAT inside the GitHub-cloned Open-Night folder and run it there.
goto :stop
:fetch_failed
echo [ERROR] GitHub could not be reached. Check your connection and Git authentication.
goto :stop
:create_failed
echo [ERROR] The map-preview branch could not be created on GitHub.
echo Run: gh auth status
goto :stop
:preview_folder_conflict
echo [ERROR] !PREVIEW_DIR! already exists but is not the expected Git worktree.
echo Rename that folder, then run this setup again.
goto :stop
:worktree_failed
echo [ERROR] The separate preview worktree could not be created.
goto :stop
:dirty
echo [ERROR] The preview worktree contains tracked edits, so it was not overwritten.
echo Open !PREVIEW_DIR! in GitHub Desktop and review those changes.
goto :stop
:diverged
echo [ERROR] Preview history diverged. Nothing was overwritten; use GitHub Desktop.
:stop
echo.
pause
exit /b 1
