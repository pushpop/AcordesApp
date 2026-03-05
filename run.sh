#!/usr/bin/env bash
# Acordes launcher for Linux / macOS
# Uses uv to manage Python versions and dependencies across platforms.
# Silent when everything is already set up — only prints when setup work is needed.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PIN_FILE="$SCRIPT_DIR/.python-version"
VENV_DIR="$SCRIPT_DIR/.venv"

# ── 1. Check if uv is installed ───────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo ""
    echo " ERROR: uv is not installed."
    echo ""
    echo " uv manages Python versions and dependencies across all platforms."
    echo ""
    echo " Install via curl:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    echo " Or via package manager:"
    echo "   macOS  : brew install uv"
    echo ""
    echo " Full instructions: https://docs.astral.sh/uv/getting-started/installation/"
    echo ""
    exit 1
fi

# ── 2. Pin Python version — only when .python-version is missing ──────────────
if [ ! -f "$PIN_FILE" ]; then
    echo " First run — setting up Acordes..."
    echo ""
    echo " Pinning Python 3.12..."

    if uv python pin 3.12 2>/dev/null; then
        echo " Pinned Python 3.12"
    elif uv python pin 3.11 2>/dev/null; then
        echo " Pinned Python 3.11"
    else
        echo ""
        echo " ERROR: Neither Python 3.12 nor 3.11 are installed."
        echo ""
        echo " Install Python via uv:  uv python install 3.12"
        echo " macOS:                  brew install python@3.12"
        echo " Ubuntu:                 sudo apt install python3.12 python3.12-venv"
        echo ""
        exit 1
    fi
fi

# ── 3. Sync dependencies — only when .venv is missing ────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    if [ ! -f "$PIN_FILE" ]; then
        # Haven't printed the header yet (venv missing but pin file existed)
        echo " First run — setting up Acordes..."
        echo ""
    fi
    echo " Installing dependencies (this may take a minute)..."

    if ! uv sync --quiet 2>&1; then
        echo ""
        echo " ================================================================"
        echo " ERROR: Dependency installation failed."
        echo " ================================================================"
        echo ""
        echo " Common fixes:"
        echo "   1. Install Python:    uv python install 3.12"
        echo "   2. Audio libraries:"
        echo "      macOS  : brew install portaudio"
        echo "      Ubuntu : sudo apt install portaudio19-dev python3-dev"
        echo "      Fedora : sudo dnf install portaudio-devel python3-devel"
        echo ""
        echo " ================================================================"
        echo ""
        exit 1
    fi

    echo " Done."
    echo ""
else
    # .venv exists — sync silently to pick up any new dependencies
    if ! uv sync --quiet 2>/dev/null; then
        echo ""
        echo " ERROR: Dependency sync failed."
        echo " Run manually for details:  uv sync"
        echo ""
        exit 1
    fi
fi

# ── 4. Launch ──────────────────────────────────────────────────────────────────
uv run python "$SCRIPT_DIR/main.py"
