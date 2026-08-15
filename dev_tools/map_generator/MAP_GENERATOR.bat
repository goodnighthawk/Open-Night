@echo off
setlocal
cd /d "%~dp0"
call SETUP_MAP_GENERATOR.bat --quiet || exit /b 1
:menu
cls
echo ============================================================
echo      OPEN NIGHT - Map + Sprite Generator v0.5.1
echo      STREET-MAP SCREENSHOTS PRIMARY // NIGHT DEFAULT
echo ============================================================
echo.
echo  1  Import ONE composite street-map screenshot
echo  2  Import ROAD-LAYOUT screenshot
echo  3  Import TRAFFIC screenshot
echo  4  Import TERRAIN screenshot
echo  5  Import TRANSIT screenshot
echo  6  Import BIKING screenshot
echo  7  Open interactive Reference Map Trace Studio
echo  8  Compile traces to STAGING semantic map (safe; does not install)
echo  9  Compile + INSTALL reference map into generator (creates backup)
echo  A  Reference status / alignment / trace folder
echo  B  Build/remake approved cosmetics + street lamps + NIGHT previews
echo  C  Save/export portable .map + editable assets
echo  D  Export semantic map + cosmetics into Open Night game folder
echo  0  Exit
echo.
choice /C 123456789ABCD0 /N /M "Choose: "
if errorlevel 14 exit /b 0
if errorlevel 13 goto exportgame
if errorlevel 12 goto portable
if errorlevel 11 "%~dp0.venv\Scripts\python.exe" map_generator.py build-cosmetics & goto pausemenu
if errorlevel 10 goto refstatus
if errorlevel 9 "%~dp0.venv\Scripts\python.exe" map_generator.py install-reference & goto pausemenu
if errorlevel 8 "%~dp0.venv\Scripts\python.exe" map_generator.py compile-reference & goto pausemenu
if errorlevel 7 "%~dp0.venv\Scripts\python.exe" map_generator.py reference-studio & goto pausemenu
if errorlevel 6 goto refbike
if errorlevel 5 goto reftransit
if errorlevel 4 goto refterrain
if errorlevel 3 goto reftraffic
if errorlevel 2 goto refroads
if errorlevel 1 goto refcomposite
:askimage
set "IMAGE="
set /p IMAGE=Full path to PNG/JPG/WebP screenshot: 
exit /b
:refcomposite
call :askimage
if not "%IMAGE%"=="" "%~dp0.venv\Scripts\python.exe" map_generator.py import-reference "%IMAGE%"
goto pausemenu
:refroads
call :askimage
if not "%IMAGE%"=="" "%~dp0.venv\Scripts\python.exe" map_generator.py import-reference-layer roads "%IMAGE%"
goto pausemenu
:reftraffic
call :askimage
if not "%IMAGE%"=="" "%~dp0.venv\Scripts\python.exe" map_generator.py import-reference-layer traffic "%IMAGE%"
goto pausemenu
:refterrain
call :askimage
if not "%IMAGE%"=="" "%~dp0.venv\Scripts\python.exe" map_generator.py import-reference-layer terrain "%IMAGE%"
goto pausemenu
:reftransit
call :askimage
if not "%IMAGE%"=="" "%~dp0.venv\Scripts\python.exe" map_generator.py import-reference-layer transit "%IMAGE%"
goto pausemenu
:refbike
call :askimage
if not "%IMAGE%"=="" "%~dp0.venv\Scripts\python.exe" map_generator.py import-reference-layer biking "%IMAGE%"
goto pausemenu
:refstatus
"%~dp0.venv\Scripts\python.exe" map_generator.py reference-status
if exist "%~dp0working_reference" start "" "%~dp0working_reference"
if exist "%~dp0output\reference_map_alignment.png" start "" "%~dp0output\reference_map_alignment.png"
if exist "%~dp0output\reference_map_composite.png" start "" "%~dp0output\reference_map_composite.png"
goto pausemenu
:portable
set "OUT=%~dp0exports"
set /p OUT=Export folder [default: %~dp0exports]: 
if "%OUT%"=="" set "OUT=%~dp0exports"
set "MAPNAME=Map_001_GWB"
set /p MAPNAME=Map filename without extension [Map_001_GWB]: 
if "%MAPNAME%"=="" set "MAPNAME=Map_001_GWB"
"%~dp0.venv\Scripts\python.exe" map_generator.py export-map "%OUT%" --name "%MAPNAME%"
goto pausemenu
:exportgame
set "GAME=%OPEN_NIGHT_GAME_ROOT%"
if defined OPEN_NIGHT_GAME_ROOT (set /p GAME=Game folder [default %OPEN_NIGHT_GAME_ROOT%]: ) else (set /p GAME=Full path to extracted Open Night game folder: )
"%~dp0.venv\Scripts\python.exe" map_generator.py export-game "%GAME%"
goto pausemenu
:pausemenu
echo.
pause
goto menu
