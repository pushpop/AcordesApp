# Acordes launcher for Windows (PowerShell)
# Uses uv to manage Python versions and dependencies across platforms.
# Silent when everything is already set up — only prints when setup work is needed.

$ErrorActionPreference = "Stop"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$PinFile    = Join-Path $ScriptDir ".python-version"
$VenvDir    = Join-Path $ScriptDir ".venv"

# ── 1. Check if uv is installed ───────────────────────────────────────────────
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host " ERROR: uv is not installed." -ForegroundColor Red
    Write-Host ""
    Write-Host " uv manages Python versions and dependencies across all platforms."
    Write-Host ""
    Write-Host " Install via PowerShell:"
    Write-Host "   powershell -ExecutionPolicy BypassUser -c 'irm https://astral.sh/uv/install.ps1 | iex'"
    Write-Host ""
    Write-Host " Full instructions: https://docs.astral.sh/uv/getting-started/installation/"
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# ── 2. Pin Python version — only when .python-version is missing ──────────────
if (-not (Test-Path $PinFile)) {
    Write-Host " First run — setting up Acordes..." -ForegroundColor Cyan
    Write-Host ""
    Write-Host " Pinning Python 3.12..."

    & uv python pin 3.12 2>$null
    if ($LASTEXITCODE -ne 0) {
        & uv python pin 3.11 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host " ERROR: Neither Python 3.12 nor 3.11 are installed." -ForegroundColor Red
            Write-Host ""
            Write-Host " Install Python via uv:  uv python install 3.12"
            Write-Host " Or from:                https://www.python.org/downloads/python-3.12.10/"
            Write-Host ""
            Read-Host "Press Enter to exit"
            exit 1
        }
        Write-Host " Pinned Python 3.11"
    } else {
        Write-Host " Pinned Python 3.12"
    }
}

# ── 3. Sync dependencies — only when .venv is missing ────────────────────────
if (-not (Test-Path $VenvDir)) {
    if (-not (Test-Path $PinFile)) {
        # Haven't printed the header yet (venv missing but pin file existed)
        Write-Host " First run — setting up Acordes..." -ForegroundColor Cyan
        Write-Host ""
    }
    Write-Host " Installing dependencies (this may take a minute)..."

    & uv sync --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host " ================================================================" -ForegroundColor Red
        Write-Host " ERROR: Dependency installation failed." -ForegroundColor Red
        Write-Host " ================================================================"
        Write-Host ""
        Write-Host " Common fixes:"
        Write-Host "   1. Install Python:   uv python install 3.12"
        Write-Host "   2. PyAudio issues:   https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        Write-Host ""
        Write-Host " ================================================================"
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }

    Write-Host " Done." -ForegroundColor Green
    Write-Host ""
} else {
    # .venv exists — sync silently to pick up any new dependencies
    & uv sync --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host " ERROR: Dependency sync failed." -ForegroundColor Red
        Write-Host " Run manually for details:  uv sync"
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ── 4. Launch ──────────────────────────────────────────────────────────────────
& uv run python (Join-Path $ScriptDir "main.py")
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host ""
    Write-Host " Acordes exited with error (code $code)." -ForegroundColor Red
    Write-Host " Check the output above for details."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit $code
}
