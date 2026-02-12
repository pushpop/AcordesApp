@echo off
REM Convenience script to run the application with the virtual environment on Windows

setlocal

set "SCRIPT_DIR=%~dp0"

if not exist "%SCRIPT_DIR%venv" (
    echo Virtual environment not found. Creating one...
    python -m venv "%SCRIPT_DIR%venv"
    echo Installing dependencies...
    if exist "%SCRIPT_DIR%venv\Scripts\pip.exe" (
        "%SCRIPT_DIR%venv\Scripts\pip.exe" install -r "%SCRIPT_DIR%requirements.txt"
    ) else (
        "%SCRIPT_DIR%venv\bin\pip.exe" install -r "%SCRIPT_DIR%requirements.txt"
    )
)

REM Support both Scripts (native Windows) and bin (Git Bash/WSL style)
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    "%SCRIPT_DIR%venv\Scripts\python.exe" "%SCRIPT_DIR%main.py"
) else (
    "%SCRIPT_DIR%venv\bin\python.exe" "%SCRIPT_DIR%main.py"
)

endlocal
