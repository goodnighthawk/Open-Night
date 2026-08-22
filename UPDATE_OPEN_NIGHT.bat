@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "PAUSE_ON_EXIT=1"
if /i "%~1"=="--launcher" set "PAUSE_ON_EXIT=0"

if /i "%OPEN_NIGHT_SKIP_UPDATE%"=="1" (call :maybe_pause & exit /b 0)
if not exist ".git\" (echo [UPDATE] This folder is not a Git installation. & call :maybe_pause & exit /b 0)

set "GIT_EXE="
for /f "delims=" %%G in ('where git.exe 2^>nul') do if not defined GIT_EXE set "GIT_EXE=%%G"
if not defined GIT_EXE if defined LOCALAPPDATA (
  for /f "delims=" %%G in ('dir /b /s "%LOCALAPPDATA%\GitHubDesktop\app-*\resources\app\git\cmd\git.exe" 2^>nul') do set "GIT_EXE=%%G"
)
if not defined GIT_EXE (
  echo [UPDATE] Git was not found. Continuing with the installed Open Night version.
  call :maybe_pause
  exit /b 0
)
set "GIT_TERMINAL_PROMPT=0"
set "GCM_INTERACTIVE=Never"
set "GIT_ASKPASS="
set "UPDATE_TIMEOUT_SECONDS=30"
set "UPDATE_WORKDIR=%CD%"

set "CURRENT_BRANCH="
for /f "delims=" %%B in ('"!GIT_EXE!" branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%B"
if /i not "!CURRENT_BRANCH!"=="main" (
  echo [UPDATE] Branch !CURRENT_BRANCH! is for development. Automatic main update skipped.
  call :maybe_pause
  exit /b 0
)

"!GIT_EXE!" diff --quiet --
if errorlevel 1 (
  echo [UPDATE] Local tracked edits detected. Nothing was overwritten; automatic update skipped.
  call :maybe_pause
  exit /b 0
)
"!GIT_EXE!" diff --cached --quiet --
if errorlevel 1 (
  echo [UPDATE] Staged edits detected. Nothing was overwritten; automatic update skipped.
  call :maybe_pause
  exit /b 0
)

echo [UPDATE] Checking GitHub main ^(maximum !UPDATE_TIMEOUT_SECONDS! seconds^)...
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
  "$git=$env:GIT_EXE; $gitArgs=@('-c','credential.interactive=never','-c','core.askPass=','-c','http.lowSpeedLimit=1024','-c','http.lowSpeedTime=15','fetch','--quiet','origin','+main:refs/remotes/origin/main'); $proc=Start-Process -FilePath $git -ArgumentList $gitArgs -WorkingDirectory $env:UPDATE_WORKDIR -NoNewWindow -PassThru; if(-not $proc.WaitForExit([int]$env:UPDATE_TIMEOUT_SECONDS * 1000)){ try { $proc.Kill() } catch {}; exit 124 }; exit $proc.ExitCode"
set "FETCH_EXIT=!ERRORLEVEL!"
if "!FETCH_EXIT!"=="124" (
  echo [UPDATE] GitHub check timed out after !UPDATE_TIMEOUT_SECONDS! seconds. Continuing offline.
  call :maybe_pause
  exit /b 0
)
if not "!FETCH_EXIT!"=="0" (
  echo [UPDATE] GitHub is unavailable. Continuing offline with the installed version.
  call :maybe_pause
  exit /b 0
)

set "LOCAL_SHA="
set "REMOTE_SHA="
for /f "delims=" %%H in ('"!GIT_EXE!" rev-parse HEAD 2^>nul') do set "LOCAL_SHA=%%H"
for /f "delims=" %%H in ('"!GIT_EXE!" rev-parse origin/main 2^>nul') do set "REMOTE_SHA=%%H"
if not defined REMOTE_SHA (echo [UPDATE] GitHub main could not be resolved. & call :maybe_pause & exit /b 0)
if /i "!LOCAL_SHA!"=="!REMOTE_SHA!" (
  set "INSTALLED_VERSION=unknown"
  if exist "VERSION.txt" set /p INSTALLED_VERSION=<"VERSION.txt"
  echo [UPDATE] Open Night v!INSTALLED_VERSION! is current.
  echo [UPDATE] Install: %CD%
  echo [UPDATE] Commit: !LOCAL_SHA!
  call :maybe_pause
  exit /b 0
)

"!GIT_EXE!" merge-base --is-ancestor HEAD origin/main >nul 2>nul
if errorlevel 1 (
  echo [UPDATE] Local history differs from GitHub main. Nothing was changed; use GitHub Desktop.
  call :maybe_pause
  exit /b 0
)

"!GIT_EXE!" merge --ff-only --quiet origin/main
if errorlevel 1 (
  echo [UPDATE] Update could not be applied safely. Nothing was overwritten; use GitHub Desktop.
  call :maybe_pause
  exit /b 0
)
echo [UPDATE] Open Night updated from GitHub. Launching the new version...
call :maybe_pause
exit /b 0

:maybe_pause
if "%PAUSE_ON_EXIT%"=="1" (
  echo.
  echo Press any key to close this updater.
  pause >nul
)
exit /b 0
