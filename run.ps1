# Convenience script to run the application with the virtual environment on Windows (PowerShell)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Check if venv exists and is a native Windows venv
$hasNativeVenv = Test-Path "$ScriptDir\venv\Scripts\python.exe"
$hasGitBashVenv = (Test-Path "$ScriptDir\venv") -and -not $hasNativeVenv

if (-not (Test-Path "$ScriptDir\venv")) {
    Write-Host "Virtual environment not found. Creating one..."
    python -m venv "$ScriptDir\venv"
    Write-Host "Installing dependencies..."
    & "$ScriptDir\venv\Scripts\pip.exe" install -r "$ScriptDir\requirements.txt"
    $hasNativeVenv = $true
} elseif ($hasGitBashVenv) {
    Write-Host "=========================================="
    Write-Host "WARNING: Git Bash style venv detected"
    Write-Host "=========================================="
    Write-Host ""
    Write-Host "Your virtual environment was created in Git Bash."
    Write-Host "PowerShell cannot use Git Bash virtual environments directly."
    Write-Host ""
    Write-Host "Please choose an option:"
    Write-Host ""
    Write-Host "  1. Use Git Bash instead:"
    Write-Host "     ./run.sh"
    Write-Host ""
    Write-Host "  2. Create a native Windows venv for PowerShell:"
    Write-Host "     - Delete the venv folder"
    Write-Host "     - Run this script again"
    Write-Host ""
    Write-Host "  3. Manually activate the Git Bash venv in PowerShell:"
    Write-Host "     python main.py"
    Write-Host ""
    exit 1
}

# Run with native Windows venv
& "$ScriptDir\venv\Scripts\python.exe" "$ScriptDir\main.py"
