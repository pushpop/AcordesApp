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

# ── 2. Install system audio dependencies (PortAudio runtime for sounddevice) ───
# sounddevice ships pre-built wheels on Windows/macOS and links to the system
# PortAudio shared library on Linux. No C compiler or headers are required.
_install_system_audio_deps() {
    if command -v dnf &>/dev/null; then
        echo " Fedora/RHEL detected — installing PortAudio runtime..."
        sudo dnf install -y portaudio 2>&1 | grep -v "^Last\|^Loaded\|^Updating\|Nothing to do" || true
    elif command -v apt-get &>/dev/null; then
        echo " Debian/Ubuntu detected — installing PortAudio runtime..."
        sudo apt-get install -y libportaudio2 2>&1 | grep -v "^Reading\|^Building\|^Hit" || true
    elif command -v pacman &>/dev/null; then
        echo " Arch Linux detected — installing PortAudio..."
        sudo pacman -S --noconfirm portaudio 2>&1 | grep -v "^warning" || true
    elif command -v brew &>/dev/null; then
        echo " macOS/Homebrew detected — installing PortAudio..."
        brew install portaudio 2>&1 | grep -v "^==> Already\|^Warning" || true
    else
        echo ""
        echo " WARNING: Could not detect package manager."
        echo " If audio fails, install the PortAudio runtime manually:"
        echo "   Fedora : sudo dnf install portaudio"
        echo "   Ubuntu : sudo apt install libportaudio2"
        echo "   Arch   : sudo pacman -S portaudio"
        echo "   macOS  : brew install portaudio"
        echo ""
    fi
}

# Check for the PortAudio shared library (runtime, not headers).
# sounddevice needs the .so at runtime; no compiler or -devel package required.
if ! ldconfig -p 2>/dev/null | grep -q libportaudio && \
   ! [ -f /usr/lib/libportaudio.so.2 ] && \
   ! [ -f /usr/local/lib/libportaudio.so.2 ] && \
   ! command -v brew &>/dev/null; then
    echo ""
    echo " PortAudio library not found — installing system dependencies..."
    _install_system_audio_deps
    echo ""
fi

# ── 3. ARM: install build deps for python-rtmidi ──────────────────────────────
# python-rtmidi has no pre-built wheel for ARM (armv7l/aarch64) and must compile
# from source. libasound2-dev and libjack-jackd2-dev provide the ALSA/JACK headers.
_ARCH="$(uname -m 2>/dev/null || echo unknown)"
if [[ "$_ARCH" == "armv7l" || "$_ARCH" == "aarch64" ]]; then
    if command -v apt-get &>/dev/null; then
        if ! dpkg -l libasound2-dev &>/dev/null 2>&1 | grep -q "^ii"; then
            echo " ARM device detected — installing build deps for python-rtmidi..."
            sudo apt-get install -y libasound2-dev libjack-jackd2-dev ninja-build libffi-dev 2>&1 | grep -v "^Reading\|^Building\|^Hit" || true
            echo ""
        fi
    fi
fi

# ── 4. Pin Python version — install automatically if missing ──────────────────
# On ARM (armv7l/aarch64) we prefer Python 3.11 because piwheels provides
# pre-built scipy/numpy wheels for cp311 but not cp312 on ARM.
if [[ "$_ARCH" == "armv7l" || "$_ARCH" == "aarch64" ]]; then
    _PY_PRIMARY="3.11"
    _PY_FALLBACK="3.12"
else
    _PY_PRIMARY="3.12"
    _PY_FALLBACK="3.11"
fi

if [ ! -f "$PIN_FILE" ]; then
    echo " First run — setting up Acordes..."
    echo ""
    echo " Pinning Python $_PY_PRIMARY..."

    if uv python pin "$_PY_PRIMARY" 2>/dev/null; then
        echo " Pinned Python $_PY_PRIMARY"
    elif uv python pin "$_PY_FALLBACK" 2>/dev/null; then
        echo " Pinned Python 3.11"
    else
        echo " Python $_PY_PRIMARY not found — installing via uv..."
        if uv python install "$_PY_PRIMARY"; then
            uv python pin "$_PY_PRIMARY"
            echo " Python $_PY_PRIMARY installed and pinned."
        else
            echo ""
            echo " ERROR: Could not install Python $_PY_PRIMARY automatically."
            echo " Try manually:  uv python install $_PY_PRIMARY"
            echo ""
            exit 1
        fi
    fi
fi

# ── 5. Sync dependencies ───────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo " Installing dependencies (this may take a minute)..."

    # On ARM, uv's resolver ignores piwheels wheels and always picks PyPI sdists,
    # which require gfortran and hours of compilation for scipy/numpy.
    # Work around this by creating the venv first and pre-installing the heavy
    # packages via pip directly from piwheels, then letting uv sync finish the rest.
    if [[ "$_ARCH" == "armv7l" || "$_ARCH" == "aarch64" ]]; then
        uv venv --quiet
        echo " ARM: fetching scipy/numpy from piwheels (pre-built ARM wheels)..."
        "$VENV_DIR/bin/pip" install --quiet --prefer-binary \
            --extra-index-url https://www.piwheels.org/simple \
            "scipy>=1.10.0" "numpy>=1.24.0" || true
        echo ""
    fi

    # Capture output; only show it on failure so the terminal stays clean.
    SYNC_LOG="$(uv sync 2>&1)" || {
        echo ""
        echo " ================================================================"
        echo " ERROR: Dependency installation failed."
        echo " ================================================================"
        echo ""
        echo "$SYNC_LOG"
        echo ""
        echo " If sounddevice failed, install the PortAudio runtime library first:"
        echo "   Fedora : sudo dnf install portaudio"
        echo "   Ubuntu : sudo apt install libportaudio2"
        echo "   Arch   : sudo pacman -S portaudio"
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

# ── 6. ASIO PortAudio DLL install (Windows/Cygwin only, no-op elsewhere) ───────
# On native Linux/macOS PortAudio is a system library — no DLL replacement needed.
# This block only runs under Cygwin or Git Bash where a .dll path might exist.
ASIO_DLL="$SCRIPT_DIR/portaudio-asio/libportaudio64bit.dll"
if [ -f "$ASIO_DLL" ]; then
    SD_DIR="$VENV_DIR/Lib/site-packages/_sounddevice_data/portaudio-binaries"
    TARGET="$SD_DIR/libportaudio64bit.dll"
    BACKUP="$SD_DIR/libportaudio64bit.dll.bak"
    if [ -d "$SD_DIR" ]; then
        if [ -f "$TARGET" ] && [ ! -f "$BACKUP" ]; then
            cp "$TARGET" "$BACKUP"
        fi
        if ! cmp -s "$ASIO_DLL" "$TARGET" 2>/dev/null; then
            cp "$ASIO_DLL" "$TARGET"
            echo " ASIO PortAudio DLL installed."
        fi
    fi
fi

# ── 7. Launch ──────────────────────────────────────────────────────────────────
uv run python "$SCRIPT_DIR/main.py"
