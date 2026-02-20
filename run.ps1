# Acordes launcher for Windows (PowerShell)
# Auto-creates a venv, installs dependencies, then runs the app.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir   = Join-Path $ScriptDir "venv"
$VenvPy    = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip   = Join-Path $VenvDir "Scripts\pip.exe"
$Reqs      = Join-Path $ScriptDir "requirements.txt"

# ── 1. Locate Python ──────────────────────────────────────────────────────────
# Prefer 'py' launcher (standard on python.org Windows installs), then 'python'.
$PythonCmd = $null
if (Get-Command "py" -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} else {
    Write-Host ""
    Write-Host " ERROR: Python was not found on PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host " Please install Python 3.11 or 3.12 from:"
    Write-Host "   https://www.python.org/downloads/"
    Write-Host ""
    Write-Host " Make sure to check 'Add Python to PATH' during installation."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# ── 2. Check Python version ───────────────────────────────────────────────────
try {
    $VerStr = & $PythonCmd -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>&1
    $Parts  = $VerStr.Trim().Split(" ")
    $PyMajor = [int]$Parts[0]
    $PyMinor = [int]$Parts[1]
} catch {
    Write-Host ""
    Write-Host " ERROR: Could not determine Python version." -ForegroundColor Red
    Write-Host " Make sure Python is installed and accessible."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

if ($PyMajor -lt 3) {
    Write-Host ""
    Write-Host " ERROR: Python 2 is not supported. Please install Python 3.11 or 3.12." -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

if ($PyMinor -lt 8) {
    Write-Host ""
    Write-Host " ERROR: Python 3.$PyMinor is too old. Minimum required: Python 3.8." -ForegroundColor Red
    Write-Host " Recommended: Python 3.11 or 3.12."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Warn on Python 3.13+ — PyAudio and python-rtmidi may not have wheels yet.
if ($PyMinor -ge 13) {
    Write-Host ""
    Write-Host " WARNING: You are using Python 3.$PyMinor." -ForegroundColor Yellow
    Write-Host ""
    Write-Host " Some dependencies (PyAudio, python-rtmidi) do not yet publish"
    Write-Host " pre-built wheels for Python 3.13+. pip will try to compile them"
    Write-Host " from source, which requires Visual Studio Build Tools."
    Write-Host ""
    Write-Host " For the easiest experience, use Python 3.11 or 3.12 instead:"
    Write-Host "   https://www.python.org/downloads/"
    Write-Host ""
    Write-Host " If you have Visual Studio Build Tools and want to proceed anyway,"
    $continue = Read-Host "press Enter to continue or Ctrl+C to cancel"
}

# ── 3. Create venv if missing ─────────────────────────────────────────────────
if (-not (Test-Path $VenvPy)) {
    # If there is a leftover venv folder without Scripts\python.exe (e.g. a Git
    # Bash venv that only has bin/) remove it so we create a clean Windows one.
    if (Test-Path $VenvDir) {
        Write-Host ""
        Write-Host " Found an incompatible virtual environment (no Scripts\python.exe)." -ForegroundColor Yellow
        Write-Host " Removing it and creating a fresh Windows venv..."
        Remove-Item -Recurse -Force $VenvDir
    }

    Write-Host ""
    Write-Host " Creating virtual environment..."
    & $PythonCmd -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host " ERROR: Failed to create virtual environment." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }

    Write-Host " Installing dependencies (this may take a minute)..."
    Write-Host ""
    & $VenvPip install --upgrade pip --quiet
    & $VenvPip install -r $Reqs

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host " ================================================================" -ForegroundColor Red
        Write-Host " ERROR: Some dependencies failed to install." -ForegroundColor Red
        Write-Host " ================================================================"
        Write-Host ""
        Write-Host " Common causes on Windows:"
        Write-Host ""
        Write-Host " 1. PyAudio / python-rtmidi have no pre-built wheel for your"
        Write-Host "    Python version. Solution: use Python 3.11 or 3.12."
        Write-Host ""
        Write-Host " 2. Missing C++ compiler for source builds. Install from:"
        Write-Host "    https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        Write-Host ""
        Write-Host " 3. Try the manual fix for PyAudio:"
        Write-Host "    pip install pipwin"
        Write-Host "    pipwin install pyaudio"
        Write-Host ""
        Write-Host " ================================================================"
        Write-Host ""
        # Clean up so next run retries from scratch.
        Remove-Item -Recurse -Force $VenvDir -ErrorAction SilentlyContinue
        Read-Host "Press Enter to exit"
        exit 1
    }

    Write-Host ""
    Write-Host " Setup complete!" -ForegroundColor Green
}

# ── 4. Launch ─────────────────────────────────────────────────────────────────
& $VenvPy (Join-Path $ScriptDir "main.py")
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host ""
    Write-Host " The application exited with an error (code $code)." -ForegroundColor Red
    Write-Host " Check the output above for details."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit $code
}
