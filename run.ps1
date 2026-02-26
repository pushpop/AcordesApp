# Acordes launcher for Windows (PowerShell)
# Auto-creates a venv, installs dependencies, then runs the app.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir   = Join-Path $ScriptDir "venv"
$VenvPy    = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip   = Join-Path $VenvDir "Scripts\pip.exe"
$Reqs      = Join-Path $ScriptDir "requirements.txt"

# ── 1. Locate Python ──────────────────────────────────────────────────────────
# If the 'py' launcher is present, try preferred versions 3.12 then 3.11 first.
# This means a user who has Python 3.12 AND 3.14 installed will automatically
# get 3.12 (which has pre-built wheels for all dependencies).
$PythonCmd  = $null
$PythonArgs = @()

if (Get-Command "py" -ErrorAction SilentlyContinue) {
    # Test each preferred version
    foreach ($ver in @("3.12", "3.11")) {
        $null = & py "-$ver" --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $PythonCmd  = "py"
            $PythonArgs = @("-$ver")
            break
        }
    }
    if (-not $PythonCmd) {
        # py launcher present but no preferred version - use its default
        $PythonCmd  = "py"
        $PythonArgs = @()
    }
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $PythonCmd  = "python"
    $PythonArgs = @()
} else {
    Write-Host ""
    Write-Host " ERROR: Python was not found on PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host " Please install Python 3.12 from:"
    Write-Host "   https://www.python.org/downloads/python-3.12.10/"
    Write-Host ""
    Write-Host " Make sure to check 'Add Python to PATH' during installation."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# ── 2. Check Python version ───────────────────────────────────────────────────
try {
    $VerStr  = & $PythonCmd @PythonArgs -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>&1
    $Parts   = $VerStr.Trim().Split(" ")
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

# Only show Python version if we need to do work (venv doesn't exist yet)
$ShowPythonVersion = -not (Test-Path $VenvPy)

if ($ShowPythonVersion -and $PythonArgs.Count -gt 0) {
    Write-Host " Using Python $PyMajor.$PyMinor (selected via py $($PythonArgs[0]))"
}

if ($PyMajor -lt 3) {
    Write-Host ""
    Write-Host " ERROR: Python 2 is not supported. Please install Python 3.12." -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

if ($PyMinor -lt 8) {
    Write-Host ""
    Write-Host " ERROR: Python 3.$PyMinor is too old. Minimum required: Python 3.8." -ForegroundColor Red
    Write-Host " Recommended: Python 3.12."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Warn on Python 3.13+ - PyAudio and python-rtmidi have no wheels yet.
if ($PyMinor -ge 13) {
    Write-Host ""
    Write-Host " WARNING: Python 3.$PyMinor detected." -ForegroundColor Yellow
    Write-Host ""
    Write-Host " Dependencies PyAudio and python-rtmidi do not yet have pre-built"
    Write-Host " wheels for Python 3.13+. pip will try to compile them from source,"
    Write-Host " which requires the Visual Studio C++ Build Tools."
    Write-Host ""
    Write-Host " Easiest fix: install Python 3.12 alongside your current version:"
    Write-Host "   https://www.python.org/downloads/python-3.12.10/"
    Write-Host ""
    Write-Host " After installing 3.12, delete the venv\ folder and run this script"
    Write-Host " again - it will automatically pick up Python 3.12."
    Write-Host ""
    Read-Host "Press Enter to attempt the install anyway, or Ctrl+C to cancel"
}

# ── 3. Create venv if missing ─────────────────────────────────────────────────
if (-not (Test-Path $VenvPy)) {
    # Remove any incompatible leftover venv (e.g. Git Bash venv with bin/ only,
    # or a venv built with a different Python version after changing the selection).
    if (Test-Path $VenvDir) {
        Write-Host ""
        Write-Host " Removing incompatible existing virtual environment..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VenvDir
    }

    Write-Host ""
    Write-Host " Creating virtual environment with Python 3.$PyMinor..."
    & $PythonCmd @PythonArgs -m venv $VenvDir
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
        Write-Host " Common fixes:"
        Write-Host ""
        Write-Host " 1. Use Python 3.12 (has pre-built wheels for all dependencies):"
        Write-Host "      https://www.python.org/downloads/python-3.12.10/"
        Write-Host "    Then delete venv\ and run this script again."
        Write-Host ""
        Write-Host " 2. Install Visual Studio C++ Build Tools for source compilation:"
        Write-Host "      https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        Write-Host ""
        Write-Host " ================================================================"
        Write-Host ""
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
