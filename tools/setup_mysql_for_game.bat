@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Python MMO - MySQL 8.4 Setup

rem ============================================================
rem Python MMO MySQL setup
rem
rem What this script does:
rem   1. Elevates itself to Administrator
rem   2. Checks that port 3306 is free
rem   3. Downloads the official MySQL Community Server 8.4 ZIP
rem   4. Verifies the download MD5
rem   5. Initializes a local MySQL data directory
rem   6. Registers and starts Windows service "MySQL84"
rem   7. Creates the "pymmo" database and game tables
rem   8. Creates a local-only application account "pymmo_game"
rem   9. Writes connection details beside this BAT file
rem  10. Tests the database connection
rem
rem It does NOT expose MySQL to the LAN/Internet:
rem bind-address is 127.0.0.1.
rem ============================================================

set "MYSQL_VERSION=8.4.11"
set "MYSQL_SERVICE=MySQL84"
set "MYSQL_ROOT=C:\MySQL84"
set "MYSQL_HOME=C:\MySQL84\mysql-8.4.11-winx64"
set "MYSQL_BIN=%MYSQL_HOME%\bin"
set "MYSQL_DATA=C:\MySQL84\data"
set "MYSQL_INI=C:\MySQL84\my.ini"

set "MYSQL_URL=https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-8.4.11-winx64.zip"
set "MYSQL_ZIP=%TEMP%\mysql-8.4.11-winx64.zip"
set "MYSQL_MD5=2e833921898a9a030ea6bfe81bd811bc"

set "DB_HOST=127.0.0.1"
set "DB_PORT=3306"
set "DB_NAME=pymmo"
set "DB_USER=pymmo_game"

set "REPORT=%~dp0mysql_setup_report.txt"
set "CREDENTIALS=%~dp0mysql_game_credentials.txt"
set "ENVFILE=%~dp0game_mysql_env.bat"
set "TEMP_SQL=%TEMP%\pymmo_mysql_setup_%RANDOM%%RANDOM%.sql"
set "TEMP_SCHEMA=%TEMP%\pymmo_schema_%RANDOM%%RANDOM%.sql"
set "OWNER_MARKER=%MYSQL_ROOT%\.pymmo_mysql_setup_owned"

rem ---------- Administrator elevation ----------
net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo.
    echo [INFO] Administrator privileges are required.
    echo [INFO] Windows will ask for permission now.
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cls
echo ============================================================
echo        Python MMO - MySQL 8.4 Automatic Setup
echo ============================================================
echo.
echo MySQL version : %MYSQL_VERSION%
echo Service name  : %MYSQL_SERVICE%
echo Install path  : %MYSQL_ROOT%
echo Database      : %DB_NAME%
echo Game user     : %DB_USER%
echo Listen address: %DB_HOST%:%DB_PORT% ^(local computer only^)
echo.
echo This can download roughly 270 MB and may take several minutes.
echo.
choice /C YN /N /M "Continue? [Y/N]: "
if errorlevel 2 exit /b 0

> "%REPORT%" echo ============================================================
>>"%REPORT%" echo Python MMO MySQL Setup Report
>>"%REPORT%" echo Started: %DATE% %TIME%
>>"%REPORT%" echo Computer: %COMPUTERNAME%
>>"%REPORT%" echo MySQL version: %MYSQL_VERSION%
>>"%REPORT%" echo Service: %MYSQL_SERVICE%
>>"%REPORT%" echo ============================================================
>>"%REPORT%" echo.

echo.
echo [1/10] Checking for an existing MySQL84 service...
sc query "%MYSQL_SERVICE%" >nul 2>&1
if "%errorlevel%"=="0" (
    echo [INFO] Service %MYSQL_SERVICE% already exists.
    >>"%REPORT%" echo [INFO] Existing service found: %MYSQL_SERVICE%
    sc qc "%MYSQL_SERVICE%" >>"%REPORT%" 2>&1

    if exist "%MYSQL_BIN%\mysql.exe" (
        echo [INFO] Existing installation matches %MYSQL_HOME%.
        goto EXISTING_SERVICE
    ) else (
        echo.
        echo [ERROR] A service named %MYSQL_SERVICE% exists, but this setup
        echo         cannot find:
        echo         %MYSQL_BIN%\mysql.exe
        echo.
        echo For safety, this script will NOT overwrite that service.
        echo See:
        echo %REPORT%
        >>"%REPORT%" echo [ERROR] Service exists but expected mysql.exe is missing.
        goto FAILED
    )
)
echo [OK] No conflicting %MYSQL_SERVICE% service found.
>>"%REPORT%" echo [OK] No existing %MYSQL_SERVICE% service.

echo.
echo [2/10] Checking TCP port %DB_PORT%...
netstat -ano -p tcp | findstr /R /C:":%DB_PORT% .*LISTENING" > "%TEMP%\pymmo_port_check.txt"
for %%A in ("%TEMP%\pymmo_port_check.txt") do set "PORTFILESIZE=%%~zA"
if not "!PORTFILESIZE!"=="0" (
    echo.
    echo [ERROR] TCP port %DB_PORT% is already in use:
    type "%TEMP%\pymmo_port_check.txt"
    >>"%REPORT%" echo [ERROR] TCP port %DB_PORT% was already in use:
    type "%TEMP%\pymmo_port_check.txt" >>"%REPORT%"
    del "%TEMP%\pymmo_port_check.txt" >nul 2>&1
    echo.
    echo Stop the program using port %DB_PORT%, then run this setup again.
    goto FAILED
)
del "%TEMP%\pymmo_port_check.txt" >nul 2>&1
echo [OK] Port %DB_PORT% is available.
>>"%REPORT%" echo [OK] Port %DB_PORT% is available.

echo.
echo [3/10] Preparing installation directory...
if exist "%MYSQL_HOME%\bin\mysqld.exe" (
    echo [INFO] MySQL files already exist at %MYSQL_HOME%.
    >>"%REPORT%" echo [INFO] Reusing existing MySQL binaries.
    goto BINARIES_READY
)

if exist "%MYSQL_ROOT%" (
    if exist "%OWNER_MARKER%" (
        echo [INFO] Reusing a setup directory created by this script.
        >>"%REPORT%" echo [INFO] Reusing owned setup directory: %MYSQL_ROOT%
    ) else (
        echo.
        echo [ERROR] %MYSQL_ROOT% already exists, but it was not created by
        echo         this setup script and the expected MySQL binaries are absent.
        echo.
        echo For safety, this script will not delete or overwrite that folder.
        >>"%REPORT%" echo [ERROR] Existing unowned directory: %MYSQL_ROOT%
        goto FAILED
    )
) else (
    mkdir "%MYSQL_ROOT%" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Could not create %MYSQL_ROOT%.
        >>"%REPORT%" echo [ERROR] Could not create install directory.
        goto FAILED
    )
    >"%OWNER_MARKER%" echo Created by setup_mysql_for_game.bat on %DATE% %TIME%
    echo [OK] Installation directory created.
)

echo.
echo [4/10] Downloading MySQL Community Server %MYSQL_VERSION%...
echo Source:
echo %MYSQL_URL%
>>"%REPORT%" echo Downloading: %MYSQL_URL%

if exist "%MYSQL_ZIP%" (
    echo [INFO] Existing download found. It will be verified first.
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%MYSQL_URL%' -OutFile '%MYSQL_ZIP%'"
    if errorlevel 1 (
        echo.
        echo [ERROR] MySQL download failed.
        >>"%REPORT%" echo [ERROR] Download failed.
        goto FAILED
    )
)

if not exist "%MYSQL_ZIP%" (
    echo [ERROR] Download file was not created.
    >>"%REPORT%" echo [ERROR] ZIP missing after download.
    goto FAILED
)

echo.
echo Verifying MD5 checksum...
set "ACTUAL_MD5="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm MD5 -LiteralPath '%MYSQL_ZIP%').Hash.ToLower()"`) do set "ACTUAL_MD5=%%H"

echo Expected: %MYSQL_MD5%
echo Actual  : !ACTUAL_MD5!
>>"%REPORT%" echo Expected MD5: %MYSQL_MD5%
>>"%REPORT%" echo Actual MD5: !ACTUAL_MD5!

if /I not "!ACTUAL_MD5!"=="%MYSQL_MD5%" (
    echo.
    echo [ERROR] Download checksum does not match Oracle's published MD5.
    echo The ZIP will be deleted. Run this setup again.
    del "%MYSQL_ZIP%" >nul 2>&1
    >>"%REPORT%" echo [ERROR] MD5 verification failed.
    goto FAILED
)
echo [OK] Download verified.

echo.
echo Extracting MySQL...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Expand-Archive -LiteralPath '%MYSQL_ZIP%' -DestinationPath '%MYSQL_ROOT%' -Force"
if errorlevel 1 (
    echo [ERROR] Could not extract MySQL.
    >>"%REPORT%" echo [ERROR] ZIP extraction failed.
    goto FAILED
)

:BINARIES_READY
if not exist "%MYSQL_BIN%\mysqld.exe" (
    echo.
    echo [ERROR] mysqld.exe is missing after extraction:
    echo %MYSQL_BIN%\mysqld.exe
    >>"%REPORT%" echo [ERROR] mysqld.exe missing.
    goto FAILED
)
if not exist "%MYSQL_BIN%\mysql.exe" (
    echo [ERROR] mysql.exe is missing after extraction.
    >>"%REPORT%" echo [ERROR] mysql.exe missing.
    goto FAILED
)
echo [OK] MySQL binaries are ready.
>>"%REPORT%" echo [OK] MySQL binaries: %MYSQL_BIN%

echo.
echo [5/10] Writing MySQL configuration...
> "%MYSQL_INI%" echo [mysqld]
>>"%MYSQL_INI%" echo basedir=C:/MySQL84/mysql-8.4.11-winx64
>>"%MYSQL_INI%" echo datadir=C:/MySQL84/data
>>"%MYSQL_INI%" echo port=%DB_PORT%
>>"%MYSQL_INI%" echo bind-address=%DB_HOST%
>>"%MYSQL_INI%" echo mysqlx-bind-address=127.0.0.1
>>"%MYSQL_INI%" echo mysqlx-port=33060
>>"%MYSQL_INI%" echo character-set-server=utf8mb4
>>"%MYSQL_INI%" echo collation-server=utf8mb4_unicode_ci
>>"%MYSQL_INI%" echo log-error=C:/MySQL84/data/pymmo_mysql.err
>>"%MYSQL_INI%" echo.
>>"%MYSQL_INI%" echo [client]
>>"%MYSQL_INI%" echo port=%DB_PORT%
>>"%MYSQL_INI%" echo default-character-set=utf8mb4

if not exist "%MYSQL_INI%" (
    echo [ERROR] Could not create %MYSQL_INI%.
    >>"%REPORT%" echo [ERROR] Could not create my.ini.
    goto FAILED
)
echo [OK] Configuration written to %MYSQL_INI%.

echo.
echo [6/10] Initializing the MySQL data directory...
if exist "%MYSQL_DATA%\mysql" (
    echo [INFO] Data directory is already initialized.
    >>"%REPORT%" echo [INFO] Existing initialized data directory found.
) else (
    if exist "%MYSQL_DATA%" (
        dir /b "%MYSQL_DATA%" 2>nul | findstr . >nul
        if not errorlevel 1 (
            echo.
            echo [ERROR] %MYSQL_DATA% exists and is not empty, but it does
            echo         not look like an initialized MySQL data directory.
            >>"%REPORT%" echo [ERROR] Non-empty unrecognized data directory.
            goto FAILED
        )
    )

    "%MYSQL_BIN%\mysqld.exe" --defaults-file="%MYSQL_INI%" --initialize-insecure --console >>"%REPORT%" 2>&1
    if errorlevel 1 (
        echo.
        echo [ERROR] MySQL data initialization failed.
        echo See the report and error log:
        echo   %REPORT%
        echo   %MYSQL_DATA%\pymmo_mysql.err
        goto FAILED
    )
    echo [OK] Data directory initialized.
)

echo.
echo [7/10] Registering Windows service %MYSQL_SERVICE%...
"%MYSQL_BIN%\mysqld.exe" --install "%MYSQL_SERVICE%" --defaults-file="%MYSQL_INI%" >>"%REPORT%" 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Could not register the MySQL Windows service.
    echo See %REPORT%
    goto FAILED
)

sc config "%MYSQL_SERVICE%" start= auto >>"%REPORT%" 2>&1
echo [OK] Service registered and configured for automatic startup.

echo.
echo [8/10] Starting MySQL...
net start "%MYSQL_SERVICE%" >>"%REPORT%" 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Windows could not start %MYSQL_SERVICE%.
    echo.
    echo Recent MySQL error log:
    if exist "%MYSQL_DATA%\pymmo_mysql.err" (
        powershell -NoProfile -Command "Get-Content -LiteralPath '%MYSQL_DATA%\pymmo_mysql.err' -Tail 30"
    )
    echo.
    echo Full setup report:
    echo %REPORT%
    goto FAILED
)

echo Waiting for MySQL to accept connections...
set "MYSQL_READY=0"
for /L %%I in (1,1,30) do (
    "%MYSQL_BIN%\mysqladmin.exe" -u root ping >nul 2>&1
    if not errorlevel 1 (
        set "MYSQL_READY=1"
        goto MYSQL_READY_NOW
    )
    timeout /t 1 /nobreak >nul
)

:MYSQL_READY_NOW
if not "!MYSQL_READY!"=="1" (
    echo.
    echo [ERROR] MySQL service started, but the server did not become ready.
    >>"%REPORT%" echo [ERROR] mysqladmin ping timed out.
    goto FAILED
)
echo [OK] MySQL is running.

echo.
echo [9/10] Creating secure accounts and the %DB_NAME% database...

for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[guid]::NewGuid().ToString('N').Substring(0,24)"`) do set "ROOT_PASS=%%P"
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[guid]::NewGuid().ToString('N').Substring(0,24)"`) do set "GAME_PASS=%%P"

if not defined ROOT_PASS (
    echo [ERROR] Could not generate root password.
    goto FAILED
)
if not defined GAME_PASS (
    echo [ERROR] Could not generate game-user password.
    goto FAILED
)

> "%TEMP_SQL%" echo ALTER USER 'root'@'localhost' IDENTIFIED BY '!ROOT_PASS!';
>>"%TEMP_SQL%" echo CREATE DATABASE IF NOT EXISTS `%DB_NAME%` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
>>"%TEMP_SQL%" echo CREATE USER IF NOT EXISTS '%DB_USER%'@'localhost' IDENTIFIED BY '!GAME_PASS!';
>>"%TEMP_SQL%" echo ALTER USER '%DB_USER%'@'localhost' IDENTIFIED BY '!GAME_PASS!';
>>"%TEMP_SQL%" echo CREATE USER IF NOT EXISTS '%DB_USER%'@'127.0.0.1' IDENTIFIED BY '!GAME_PASS!';
>>"%TEMP_SQL%" echo ALTER USER '%DB_USER%'@'127.0.0.1' IDENTIFIED BY '!GAME_PASS!';
>>"%TEMP_SQL%" echo GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON `%DB_NAME%`.* TO '%DB_USER%'@'localhost';
>>"%TEMP_SQL%" echo GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON `%DB_NAME%`.* TO '%DB_USER%'@'127.0.0.1';
>>"%TEMP_SQL%" echo FLUSH PRIVILEGES;

"%MYSQL_BIN%\mysql.exe" -u root < "%TEMP_SQL%" >>"%REPORT%" 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Could not configure MySQL accounts/database.
    del "%TEMP_SQL%" >nul 2>&1
    goto FAILED
)
del "%TEMP_SQL%" >nul 2>&1
echo [OK] Database and local game account created.

echo.
echo Creating Python MMO schema...
if exist "%~dp0mysql_schema.sql" (
    echo [INFO] Found mysql_schema.sql beside this setup file.
    echo [INFO] Importing the project's schema...
    "%MYSQL_BIN%\mysql.exe" -u root -p!ROOT_PASS! < "%~dp0mysql_schema.sql" >>"%REPORT%" 2>&1
    if errorlevel 1 (
        echo [ERROR] mysql_schema.sql import failed.
        goto FAILED
    )
) else (
    echo [INFO] mysql_schema.sql was not beside this BAT.
    echo [INFO] Creating the current Python MMO tables directly.

    > "%TEMP_SCHEMA%" echo USE `%DB_NAME%`;
    >>"%TEMP_SCHEMA%" echo CREATE TABLE IF NOT EXISTS player_accounts ^(
    >>"%TEMP_SCHEMA%" echo   phone VARCHAR^(20^) PRIMARY KEY,
    >>"%TEMP_SCHEMA%" echo   display_name VARCHAR^(32^) NOT NULL,
    >>"%TEMP_SCHEMA%" echo   cash INT NOT NULL DEFAULT 200,
    >>"%TEMP_SCHEMA%" echo   created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    >>"%TEMP_SCHEMA%" echo   updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    >>"%TEMP_SCHEMA%" echo ^) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    >>"%TEMP_SCHEMA%" echo CREATE TABLE IF NOT EXISTS inventory_slots ^(
    >>"%TEMP_SCHEMA%" echo   phone VARCHAR^(20^) NOT NULL,
    >>"%TEMP_SCHEMA%" echo   slot_index SMALLINT UNSIGNED NOT NULL,
    >>"%TEMP_SCHEMA%" echo   item_id VARCHAR^(64^) NOT NULL,
    >>"%TEMP_SCHEMA%" echo   quantity INT UNSIGNED NOT NULL,
    >>"%TEMP_SCHEMA%" echo   PRIMARY KEY ^(phone, slot_index^),
    >>"%TEMP_SCHEMA%" echo   CONSTRAINT fk_inventory_phone FOREIGN KEY ^(phone^) REFERENCES player_accounts^(phone^) ON DELETE CASCADE
    >>"%TEMP_SCHEMA%" echo ^) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    "%MYSQL_BIN%\mysql.exe" --protocol=TCP -h %DB_HOST% -P %DB_PORT% -u %DB_USER% -p!GAME_PASS! -D %DB_NAME% < "%TEMP_SCHEMA%" >>"%REPORT%" 2>&1
    if errorlevel 1 (
        echo [ERROR] Built-in schema creation failed.
        del "%TEMP_SCHEMA%" >nul 2>&1
        goto FAILED
    )
    del "%TEMP_SCHEMA%" >nul 2>&1
)
echo [OK] Python MMO schema is ready.

echo.
echo Writing game connection files...
> "%CREDENTIALS%" echo Python MMO MySQL credentials
>>"%CREDENTIALS%" echo Created=%DATE% %TIME%
>>"%CREDENTIALS%" echo.
>>"%CREDENTIALS%" echo MYSQL_SERVICE=%MYSQL_SERVICE%
>>"%CREDENTIALS%" echo MYSQL_HOST=%DB_HOST%
>>"%CREDENTIALS%" echo MYSQL_PORT=%DB_PORT%
>>"%CREDENTIALS%" echo MYSQL_DATABASE=%DB_NAME%
>>"%CREDENTIALS%" echo MYSQL_USER=%DB_USER%
>>"%CREDENTIALS%" echo MYSQL_PASSWORD=!GAME_PASS!
>>"%CREDENTIALS%" echo.
>>"%CREDENTIALS%" echo MYSQL_ROOT_USER=root
>>"%CREDENTIALS%" echo MYSQL_ROOT_PASSWORD=!ROOT_PASS!
>>"%CREDENTIALS%" echo.
>>"%CREDENTIALS%" echo MYSQL_HOME=%MYSQL_HOME%
>>"%CREDENTIALS%" echo MYSQL_INI=%MYSQL_INI%

> "%ENVFILE%" echo @echo off
>>"%ENVFILE%" echo rem Generated by setup_mysql_for_game.bat
>>"%ENVFILE%" echo rem MYSQL_* names:
>>"%ENVFILE%" echo set "MYSQL_HOST=%DB_HOST%"
>>"%ENVFILE%" echo set "MYSQL_PORT=%DB_PORT%"
>>"%ENVFILE%" echo set "MYSQL_DATABASE=%DB_NAME%"
>>"%ENVFILE%" echo set "MYSQL_USER=%DB_USER%"
>>"%ENVFILE%" echo set "MYSQL_PASSWORD=!GAME_PASS!"
>>"%ENVFILE%" echo rem Common DB_* aliases:
>>"%ENVFILE%" echo set "DB_HOST=%DB_HOST%"
>>"%ENVFILE%" echo set "DB_PORT=%DB_PORT%"
>>"%ENVFILE%" echo set "DB_NAME=%DB_NAME%"
>>"%ENVFILE%" echo set "DB_USER=%DB_USER%"
>>"%ENVFILE%" echo set "DB_PASSWORD=!GAME_PASS!"
>>"%ENVFILE%" echo rem Project-specific PYMMO_* aliases:
>>"%ENVFILE%" echo set "PYMMO_DB_HOST=%DB_HOST%"
>>"%ENVFILE%" echo set "PYMMO_DB_PORT=%DB_PORT%"
>>"%ENVFILE%" echo set "PYMMO_DB_NAME=%DB_NAME%"
>>"%ENVFILE%" echo set "PYMMO_DB_USER=%DB_USER%"
>>"%ENVFILE%" echo set "PYMMO_DB_PASSWORD=!GAME_PASS!"
>>"%ENVFILE%" echo set "PATH=%MYSQL_BIN%;%%PATH%%"

echo [OK] Credentials: %CREDENTIALS%
echo [OK] Environment: %ENVFILE%

echo.
echo [10/10] Testing database connection...
"%MYSQL_BIN%\mysql.exe" --protocol=TCP -h %DB_HOST% -P %DB_PORT% -u %DB_USER% -p!GAME_PASS! -D %DB_NAME% -e "SELECT VERSION() AS mysql_version; SHOW TABLES;" >>"%REPORT%" 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Final database connection test failed.
    goto FAILED
)
echo [OK] Database login and schema test succeeded.

rem Optional Python connector installation if this server.py explicitly imports it.
if exist "%~dp0server.py" (
    findstr /I /C:"mysql.connector" "%~dp0server.py" >nul 2>&1
    if not errorlevel 1 (
        echo.
        echo [INFO] server.py imports mysql.connector.
        echo [INFO] Installing mysql-connector-python for the active Python...
        where py >nul 2>&1
        if not errorlevel 1 (
            py -m pip install mysql-connector-python >>"%REPORT%" 2>&1
        ) else (
            where python >nul 2>&1
            if not errorlevel 1 (
                python -m pip install mysql-connector-python >>"%REPORT%" 2>&1
            )
        )
    )
)

echo.
echo ============================================================
echo                 SETUP COMPLETE
echo ============================================================
echo.
echo MySQL service : %MYSQL_SERVICE%
echo Server         : %DB_HOST%:%DB_PORT%
echo Database       : %DB_NAME%
echo Game user      : %DB_USER%
echo.
echo Connection details were saved to:
echo   %CREDENTIALS%
echo.
echo Before starting a server that reads MYSQL_* environment
echo variables, run:
echo.
echo   call "%ENVFILE%"
echo.
echo Then start the game server normally, for example:
echo.
echo   py server.py
echo.
echo Setup report:
echo   %REPORT%
echo.
echo IMPORTANT: mysql_game_credentials.txt contains passwords.
echo Keep it private.
echo.
pause
exit /b 0


:EXISTING_SERVICE
echo.
echo ============================================================
echo Existing MySQL84 installation detected
echo ============================================================
echo.
echo This setup deliberately does not reset an existing root password.
echo Attempting to start the service...
net start "%MYSQL_SERVICE%" >>"%REPORT%" 2>&1
sc query "%MYSQL_SERVICE%" | find "RUNNING" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Existing MySQL84 service could not be started.
    goto FAILED
)
echo [OK] Existing %MYSQL_SERVICE% service is running.
echo.
echo The automatic fresh-install path was skipped to protect the
echo existing database/passwords.
echo.
echo If this is a partial installation left by an earlier failed setup,
echo send me:
echo   %REPORT%
echo and the contents of:
echo   %MYSQL_DATA%\pymmo_mysql.err
echo.
pause
exit /b 0


:FAILED
echo.
echo ============================================================
echo                    SETUP FAILED
echo ============================================================
echo.
echo Setup stopped at the failing step. No further setup actions will run.
echo.
echo Send me this report:
echo   %REPORT%
echo.
if exist "%MYSQL_DATA%\pymmo_mysql.err" (
    echo Also send this MySQL error log:
    echo   %MYSQL_DATA%\pymmo_mysql.err
    echo.
)
echo The setup can usually be safely run again after the reported
echo problem is corrected.
echo.
pause
exit /b 1
