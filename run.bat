@echo off
REM Acordes launcher for Windows (Command Prompt)
REM Auto-creates a venv, installs dependencies, then runs the app.

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
REM Strip trailing backslash
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "VENV_DIR=%SCRIPT_DIR%\venv"
set "PYTHON_EXE="

REM ── 1. Locate Python ─────────────────────────────────────────────────────────
REM Prefer 'py' launcher (installed with python.org installer) then 'python'.
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=py"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 (
        set "PYTHON_CMD=python"
    ) else (
        echo.
        echo  ERROR: Python was not found on PATH.
        echo.
        echo  Please install Python 3.11 or 3.12 from:
        echo    https://www.python.org/downloads/
        echo.
        echo  Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
)

REM ── 2. Check Python version ───────────────────────────────────────────────────
REM We need 3.8+, but PyAudio/rtmidi have no wheels for 3.13+ yet.
REM Warn clearly rather than letting pip fail with cryptic errors.
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
    echo  ERROR: Python 2 is not supported. Please install Python 3.11 or 3.12.
    echo.
    pause
    exit /b 1
)

if !PY_MINOR! LSS 8 (
    echo.
    echo  ERROR: Python 3.!PY_MINOR! is too old. Minimum required: Python 3.8.
    echo  Recommended: Python 3.11 or 3.12.
    echo.
    pause
    exit /b 1
)

REM Warn on Python 3.13+ — PyAudio and python-rtmidi may not have wheels yet.
if !PY_MINOR! GEQ 13 (
    echo.
    echo  WARNING: You are using Python 3.!PY_MINOR!.
    echo.
    echo  Some dependencies (PyAudio, python-rtmidi) do not yet publish
    echo  pre-built wheels for Python 3.13+. pip will try to compile them
    echo  from source, which requires Visual Studio Build Tools.
    echo.
    echo  For the easiest experience, use Python 3.11 or 3.12 instead:
    echo    https://www.python.org/downloads/
    echo.
    echo  If you have Visual Studio Build Tools installed and want to proceed
    echo  anyway, press any key to continue. Otherwise close this window.
    echo.
    pause
)

REM ── 3. Create venv if missing ─────────────────────────────────────────────────
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo.
    echo  Creating virtual environment...
    !PYTHON_CMD! -m venv "%VENV_DIR%"
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo  ERROR: Failed to create virtual environment.
        echo  Try running: !PYTHON_CMD! -m venv "%VENV_DIR%"
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
        echo  Common causes on Windows:
        echo.
        echo  1. PyAudio / python-rtmidi have no pre-built wheel for your
        echo     Python version. Solution: use Python 3.11 or 3.12.
        echo.
        echo  2. Missing C++ compiler for source builds. Install from:
        echo     https://visualstudio.microsoft.com/visual-cpp-build-tools/
        echo.
        echo  3. Try the manual fix for PyAudio:
        echo     pip install pipwin
        echo     pipwin install pyaudio
        echo.
        echo  ================================================================
        echo.
        REM Clean up the broken venv so next run retries from scratch.
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
