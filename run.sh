#!/usr/bin/env bash
# Acordes launcher for Linux / macOS
# Auto-creates a venv, installs dependencies, then runs the app.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/venv"

# ── 1. Locate Python ──────────────────────────────────────────────────────────
# Prefer python3 (always correct on Linux/macOS) then python.
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo ""
    echo " ERROR: Python was not found on PATH."
    echo ""
    echo " Install Python 3.11 or 3.12 via your package manager:"
    echo "   macOS  : brew install python@3.12"
    echo "   Ubuntu : sudo apt install python3.12 python3.12-venv"
    echo "   Fedora : sudo dnf install python3.12"
    echo ""
    exit 1
fi

# ── 2. Check Python version ───────────────────────────────────────────────────
PY_VER=$($PYTHON_CMD -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>&1)
PY_MAJOR=$(echo "$PY_VER" | awk '{print $1}')
PY_MINOR=$(echo "$PY_VER" | awk '{print $2}')

if [ -z "$PY_MAJOR" ]; then
    echo ""
    echo " ERROR: Could not determine Python version."
    echo ""
    exit 1
fi

if [ "$PY_MAJOR" -lt 3 ]; then
    echo ""
    echo " ERROR: Python 2 is not supported. Please use Python 3.11 or 3.12."
    echo ""
    exit 1
fi

if [ "$PY_MINOR" -lt 8 ]; then
    echo ""
    echo " ERROR: Python 3.$PY_MINOR is too old. Minimum required: Python 3.8."
    echo " Recommended: Python 3.11 or 3.12."
    echo ""
    exit 1
fi

# Warn on 3.13+ — some wheels may be missing.
if [ "$PY_MINOR" -ge 13 ]; then
    echo ""
    echo " WARNING: You are using Python 3.$PY_MINOR."
    echo ""
    echo " Some dependencies (PyAudio, python-rtmidi) may not yet have"
    echo " pre-built wheels for Python 3.13+. If installation fails, try"
    echo " Python 3.11 or 3.12, or install the system PortAudio library first:"
    echo "   macOS  : brew install portaudio"
    echo "   Ubuntu : sudo apt install portaudio19-dev"
    echo "   Fedora : sudo dnf install portaudio-devel"
    echo ""
fi

# ── 3. Create venv if missing ─────────────────────────────────────────────────
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo ""
    echo " Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"

    echo " Installing dependencies (this may take a minute)..."
    echo ""
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

    if [ $? -ne 0 ]; then
        echo ""
        echo " ================================================================"
        echo " ERROR: Some dependencies failed to install."
        echo " ================================================================"
        echo ""
        echo " Common causes:"
        echo ""
        echo " 1. Missing system audio libraries. Install them first:"
        echo "    macOS  : brew install portaudio"
        echo "    Ubuntu : sudo apt install portaudio19-dev python3-dev"
        echo "    Fedora : sudo dnf install portaudio-devel python3-devel"
        echo ""
        echo " 2. Python 3.13+ — some wheels require source compilation."
        echo "    Use Python 3.11 or 3.12 for a smoother install."
        echo ""
        echo " ================================================================"
        echo ""
        # Clean up so the next run retries from scratch.
        rm -rf "$VENV_DIR"
        exit 1
    fi

    echo ""
    echo " Setup complete!"
fi

# ── 4. Launch ─────────────────────────────────────────────────────────────────
"$VENV_DIR/bin/python" "$SCRIPT_DIR/main.py"
