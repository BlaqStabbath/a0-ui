@echo off
setlocal enabledelayedexpansion

REM a0-ui Windows installer / updater
REM - First run: creates .venv, installs requirements, registers a Start Menu shortcut.
REM - Re-run: skips venv creation, runs pip install -r requirements.txt (upgrades),
REM   rewrites the shortcut, warns if the previously-registered path no longer exists.

set "HERE=%~dp0"
cd /d "%HERE%"

REM 1. Detect first install vs update
if exist ".venv\Scripts\python.exe" (
    set "MODE=update"
    echo === a0-ui update ===
) else (
    set "MODE=first-install"
    echo === a0-ui first install ===
)
echo Project directory: %HERE%
echo.

REM 2. Locate Python (prefer py launcher, then python3, then python)
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY=py -3"
) else (
    where python3 >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set "PY=python3"
    ) else (
        where python >nul 2>nul
        if %ERRORLEVEL% EQU 0 (
            set "PY=python"
        ) else (
            echo ERROR: Python 3.10+ not found. Install it from https://python.org/downloads/
            echo Make sure to tick "Add Python to PATH" during installation.
            pause
            exit /b 1
        )
    )
)

echo Using Python: %PY%
%PY% --version

REM 3. Create venv if missing
if "!MODE!"=="first-install" (
    if not exist ".venv\Scripts\python.exe" (
        echo Creating virtual environment...
        %PY% -m venv .venv
        if errorlevel 1 (
            echo ERROR: Failed to create virtual environment.
            pause
            exit /b 1
        )
    )
)

REM 4. Install/upgrade dependencies
echo Installing dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

REM 5. Validate the previously-registered shortcut (if any)
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Agent Zero.lnk"
if exist "%SHORTCUT%" (
    for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.WorkingDirectory"`) do (
        set "OLDWD=%%P"
    )
    if defined OLDWD if not exist "!OLDWD!" (
        echo.
        echo WARNING: previous install pointed at !OLDWD! which no longer exists.
        echo          this install registers: %HERE%
    )
)

REM 6. Create/refresh the Start Menu shortcut
set "TARGET=%HERE%.venv\Scripts\python.exe"
set "ARGS=-m a0_ui"
set "WORKDIR=%HERE%"
set "ICON=%HERE%icons\icon.svg"

echo Creating Start Menu shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.Arguments = '%ARGS%';" ^
  "$s.WorkingDirectory = '%WORKDIR%';" ^
  "$s.IconLocation = '%ICON%,0';" ^
  "$s.Description = 'Agent Zero desktop UI';" ^
  "$s.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo Installed: %SHORTCUT%
    echo You can launch Agent Zero from the Start Menu.
) else (
    echo WARNING: Could not create Start Menu shortcut. You can run the app manually:
    echo   %TARGET% -m a0_ui
)

echo.
echo === Installation complete ===
pause
