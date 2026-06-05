@echo off
setlocal enabledelayedexpansion

REM a0-ui Windows installer
REM Creates a .venv, installs dependencies, and registers a Start Menu shortcut.

set "HERE=%~dp0"
cd /d "%HERE%"

echo === a0-ui Windows installer ===
echo Project directory: %HERE%
echo.

REM 1. Locate Python (prefer py launcher, then python3, then python)
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

REM 2. Create .venv if it does not exist
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM 3. Install/upgrade dependencies
echo Installing dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

REM 4. Create Start Menu shortcut using PowerShell
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Agent Zero.lnk"
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
