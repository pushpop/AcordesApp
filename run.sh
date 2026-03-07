#!/usr/bin/env bash
# ABOUTME: Acordes launcher for Linux / macOS.
# ABOUTME: Auto-installs uv, Python, system audio deps, and all Python dependencies.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PIN_FILE="$SCRIPT_DIR/.python-version"
VENV_DIR="$SCRIPT_DIR/.venv"

# ── 1. Auto-install uv if missing ─────────────────────────────────────────────
# Extend PATH to include common uv install locations so the command -v check
# works even in non-interactive shells that may have a minimal PATH.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

if ! command -v uv &>/dev/null; then
    echo ""
    echo " uv not found — installing automatically..."
    echo ""
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        # Reload PATH so the newly installed uv is found
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        if ! command -v uv &>/dev/null; then
            echo ""
            echo " uv was installed but not found in PATH."
            echo " Please restart your terminal and run ./run.sh again."
            echo " Or add to PATH:  export PATH=\"\$HOME/.local/bin:\$PATH\""
            echo ""
            exit 1
        fi
        echo " uv installed successfully."
        echo ""
    else
        echo ""
        echo " ERROR: Automatic uv installation failed."
        echo ""
        echo " Please install manually:"
        echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "   source ~/.bashrc   (or restart your terminal)"
        echo ""
        echo " Package manager alternatives:"
        echo "   Fedora : sudo dnf install uv"
        echo "   Ubuntu : sudo apt install uv"
        echo "   macOS  : brew install uv"
        echo ""
        exit 1
    fi
fi

# ── 2. Install system audio dependencies (required to compile PyAudio) ─────────
# PyAudio requires PortAudio headers and a C compiler to build from source.
# Detect the package manager and install deps before attempting uv sync.
_install_system_audio_deps() {
    if command -v dnf &>/dev/null; then
        echo " Fedora/RHEL detected — installing audio build dependencies..."
        sudo dnf install -y portaudio-devel python3-devel gcc 2>&1 | grep -v "^Last\|^Loaded\|^Updating\|Nothing to do" || true
    elif command -v apt-get &>/dev/null; then
        echo " Debian/Ubuntu detected — installing audio build dependencies..."
        sudo apt-get install -y portaudio19-dev python3-dev gcc 2>&1 | grep -v "^Reading\|^Building\|^Hit" || true
    elif command -v pacman &>/dev/null; then
        echo " Arch Linux detected — installing audio build dependencies..."
        sudo pacman -S --noconfirm portaudio python gcc 2>&1 | grep -v "^warning" || true
    elif command -v brew &>/dev/null; then
        echo " macOS/Homebrew detected — installing PortAudio..."
        brew install portaudio 2>&1 | grep -v "^==> Already\|^Warning" || true
    else
        echo ""
        echo " WARNING: Could not detect package manager."
        echo " If the build fails, install these packages manually:"
        echo "   Fedora : sudo dnf install portaudio-devel python3-devel gcc"
        echo "   Ubuntu : sudo apt install portaudio19-dev python3-dev gcc"
        echo "   Arch   : sudo pacman -S portaudio python gcc"
        echo "   macOS  : brew install portaudio"
        echo ""
    fi
}

# Only run system dep install if portaudio headers are not already present
if ! pkg-config --exists portaudio-2.0 2>/dev/null && \
   ! [ -f /usr/include/portaudio.h ] && \
   ! [ -f /usr/local/include/portaudio.h ]; then
    echo ""
    echo " PortAudio headers not found — installing system dependencies..."
    _install_system_audio_deps
    echo ""
fi

# ── 3. Pin Python version — install automatically if missing ──────────────────
if [ ! -f "$PIN_FILE" ]; then
    echo " First run — setting up Acordes..."
    echo ""
    echo " Pinning Python 3.12..."

    if uv python pin 3.12 2>/dev/null; then
        echo " Pinned Python 3.12"
    elif uv python pin 3.11 2>/dev/null; then
        echo " Pinned Python 3.11"
    else
        echo " Python 3.12 not found — installing via uv..."
        if uv python install 3.12; then
            uv python pin 3.12
            echo " Python 3.12 installed and pinned."
        else
            echo ""
            echo " ERROR: Could not install Python 3.12 automatically."
            echo " Try manually:  uv python install 3.12"
            echo ""
            exit 1
        fi
    fi
fi

# ── 4. Sync dependencies ───────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo " Installing dependencies (this may take a minute)..."

    # Capture output; only show it on failure so the terminal stays clean.
    SYNC_LOG="$(uv sync 2>&1)" || {
        echo ""
        echo " ================================================================"
        echo " ERROR: Dependency installation failed."
        echo " ================================================================"
        echo ""
        echo "$SYNC_LOG"
        echo ""
        echo " If PyAudio failed to build, install system audio libraries first:"
        echo "   Fedora : sudo dnf install portaudio-devel python3-devel gcc"
        echo "   Ubuntu : sudo apt install portaudio19-dev python3-dev gcc"
        echo "   Arch   : sudo pacman -S portaudio python gcc"
        echo "   macOS  : brew install portaudio"
        echo ""
        echo " Then run ./run.sh again."
        echo " ================================================================"
        echo ""
        exit 1
    }

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

# ── 5. Launch ──────────────────────────────────────────────────────────────────
uv run python "$SCRIPT_DIR/main.py"
