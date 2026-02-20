@echo off
REM Acordes launcher for Windows (Command Prompt)
REM Auto-creates a venv, installs dependencies, then runs the app.

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
REM Strip trailing backslash
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "VENV_DIR=%SCRIPT_DIR%\venv"
set "PYTHON_CMD="

REM ── 1. Locate Python ─────────────────────────────────────────────────────────
REM If the 'py' launcher is available, try preferred versions 3.12 then 3.11
REM before falling back to whatever 'py' defaults to. This means users who
REM have both Python 3.12 and 3.14 installed will automatically get 3.12,
REM which has pre-built wheels for all dependencies.
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3.12 --version >nul 2>&1
    if !ERRORLEVEL!==0 (
        set "PYTHON_CMD=py -3.12"
        goto :version_ok
    )
    py -3.11 --version >nul 2>&1
    if !ERRORLEVEL!==0 (
        set "PYTHON_CMD=py -3.11"
        goto :version_ok
    )
    REM No preferred version found — use py default and warn below if too new
    set "PYTHON_CMD=py"
    goto :version_ok
)

REM No py launcher — fall back to 'python'
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=python"
    goto :version_ok
)

echo.
echo  ERROR: Python was not found on PATH.
echo.
echo  Please install Python 3.12 from:
echo    https://www.python.org/downloads/python-3.12.10/
echo.
echo  Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:version_ok
REM ── 2. Check Python version ───────────────────────────────────────────────────
for /f "tokens=*" %%V in ('!PYTHON_CMD! -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2^>^&1') do set PY_VER=%%V

for /f "tokens=1,2" %%A in ("!PY_VER!") do (
    set PY_MAJOR=%%A
    set PY_MINOR=%%B
)

if "!PY_MAJOR!"=="" (
    echo.
    echo  ERROR: Could not determine Python version.
    echo  Make sure Python is installed and accessible.
    echo.
    pause
    exit /b 1
)

if !PY_MAJOR! LSS 3 (
    echo.
    echo  ERROR: Python 2 is not supported. Please install Python 3.12.
    echo.
    pause
    exit /b 1
)

if !PY_MINOR! LSS 8 (
    echo.
    echo  ERROR: Python 3.!PY_MINOR! is too old. Minimum required: Python 3.8.
    echo  Recommended: Python 3.12.
    echo.
    pause
    exit /b 1
)

REM Warn on Python 3.13+ — PyAudio and python-rtmidi have no wheels yet.
if !PY_MINOR! GEQ 13 (
    echo.
    echo  WARNING: Python 3.!PY_MINOR! detected.
    echo.
    echo  Dependencies PyAudio and python-rtmidi do not yet have pre-built
    echo  wheels for Python 3.13+. pip will try to compile them from source,
    echo  which requires the Visual Studio C++ Build Tools.
    echo.
    echo  Easiest fix: install Python 3.12 alongside your current version:
    echo    https://www.python.org/downloads/python-3.12.10/
    echo.
    echo  After installing 3.12, delete the venv\ folder and run this script
    echo  again — it will automatically pick up Python 3.12.
    echo.
    echo  Press any key to attempt the install anyway, or close this window.
    echo.
    pause
)

REM ── 3. Create venv if missing ─────────────────────────────────────────────────
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo.
    echo  Creating virtual environment with !PYTHON_CMD! (Python 3.!PY_MINOR!)...
    !PYTHON_CMD! -m venv "%VENV_DIR%"
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo  ERROR: Failed to create virtual environment.
        echo.
        pause
        exit /b 1
    )

    echo  Installing dependencies (this may take a minute)...
    echo.
    "%VENV_DIR%\Scripts\pip.exe" install --upgrade pip --quiet
    "%VENV_DIR%\Scripts\pip.exe" install -r "%SCRIPT_DIR%\requirements.txt"

    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo  ================================================================
        echo  ERROR: Some dependencies failed to install.
        echo  ================================================================
        echo.
        echo  Common fixes:
        echo.
        echo  1. Use Python 3.12 (has pre-built wheels for all dependencies):
        echo       https://www.python.org/downloads/python-3.12.10/
        echo     Then delete venv\ and run this script again.
        echo.
        echo  2. Install Visual Studio C++ Build Tools for source compilation:
        echo       https://visualstudio.microsoft.com/visual-cpp-build-tools/
        echo.
        echo  ================================================================
        echo.
        REM Clean up so next run retries from scratch.
        rmdir /s /q "%VENV_DIR%"
        pause
        exit /b 1
    )

    echo.
    echo  Setup complete!
)

REM ── 4. Launch ─────────────────────────────────────────────────────────────────
"%VENV_DIR%\Scripts\python.exe" "%SCRIPT_DIR%\main.py"
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo  The application exited with an error (code !ERRORLEVEL!).
    echo  Check the output above for details.
    echo.
    pause
)

endlocal
