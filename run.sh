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

# ── 3. ARM: install build deps + set console font ─────────────────────────────
# python-rtmidi has no pre-built wheel for ARM (armv7l/aarch64) and must compile
# from source. libasound2-dev and libjack-jackd2-dev provide the ALSA/JACK headers.
# scipy/numpy may also build from source if piwheels wheels are unavailable;
# gfortran and python3-dev are required by their meson/numpy build systems.
_ARCH="$(uname -m 2>/dev/null || echo unknown)"
if [[ "$_ARCH" == "armv7l" || "$_ARCH" == "aarch64" ]]; then
    if command -v apt-get &>/dev/null; then
        if ! dpkg -l libasound2-dev &>/dev/null 2>&1 | grep -q "^ii"; then
            echo " ARM device detected — installing build deps..."
            sudo apt-get install -y \
                libasound2-dev libjack-jackd2-dev ninja-build libffi-dev \
                gfortran python3-dev \
                libopenblas0 \
                2>&1 | grep -v "^Reading\|^Building\|^Hit" || true
            echo ""
        fi
    fi

    # Set a bold compact console font so the TFT framebuffer (790x600) gives
    # ~112 cols at 7x14px. The default 8x16 font only yields 98 cols and is thin.
    # Only applies when running on a real framebuffer console (not over SSH/tmux).
    _FONT="/usr/share/consolefonts/Lat15-TerminusBold14.psf.gz"
    if [[ -f "$_FONT" && "$(tty)" == /dev/tty* ]]; then
        setfont "$_FONT" 2>/dev/null || true
    fi

    # ── Real-time audio system tweaks (Patchbox-style) ────────────────────────
    # These mirror what Patchbox OS configures for low-latency audio on Pi.
    # Each tweak is attempted silently and skipped if it fails (no sudo rights, etc.)

    # 1. CPU governor: switch to 'performance' to prevent frequency scaling
    #    stalls that cause xruns. Pi 4 defaults to 'ondemand' which can drop
    #    frequency mid-callback.
    if [[ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]]; then
        echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor \
            >/dev/null 2>&1 || true
    fi

    # 2. RT scheduling limits: allow the audio group to use real-time priority
    #    without CAP_SYS_NICE. Patchbox writes these to limits.conf; we add them
    #    only if not already present.
    _LIMITS="/etc/security/limits.conf"
    if [[ -f "$_LIMITS" ]] && ! grep -q "rtprio.*95" "$_LIMITS" 2>/dev/null; then
        printf "@audio - rtprio 95\n@audio - memlock unlimited\n" \
            | sudo tee -a "$_LIMITS" >/dev/null 2>&1 || true
        # Add current user to audio group if not already a member.
        sudo usermod -aG audio "$(whoami)" 2>/dev/null || true
    fi

    # 3. Reduce VM swappiness so the kernel prefers keeping audio buffers in RAM.
    #    Default is 60; Patchbox uses 10.
    sudo sysctl -q vm.swappiness=10 2>/dev/null || true
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

    if [[ "$_ARCH" == "armv7l" || "$_ARCH" == "aarch64" ]]; then
        # ── ARM install path ───────────────────────────────────────────────────
        # uv pip resolves scipy/numpy from PyPI sdist (no armv7l wheels there),
        # triggering a multi-hour source compile. pip handles piwheels correctly
        # with --index-url, so we use pip for the heavy scientific packages and
        # uv pip for everything else.
        uv venv --seed --quiet   # --seed includes pip in the venv
        echo " ARM: installing scipy/numpy from piwheels (pre-built wheels)..."
        # Pin numpy<2.0 and scipy<1.14: piwheels 2.x wheels require glibc 2.34
        # (Debian 12 Bookworm), but Raspbian 11 (Bullseye) only has glibc 2.31.
        # numpy 1.26.4 and scipy 1.13.x are the last releases built for glibc 2.31.
        "$VENV_DIR/bin/pip" install --quiet \
            --index-url https://www.piwheels.org/simple \
            --extra-index-url https://pypi.org/simple \
            "numpy>=1.24.0,<2.0" "scipy>=1.10.0,<1.14.0" || {
                echo " ERROR: scipy/numpy install failed."
                exit 1
            }
        echo " ARM: installing remaining dependencies..."
        # Pass the same numpy/scipy upper bounds so uv accepts the piwheels
        # wheels already in the venv and does not re-resolve to a newer sdist.
        uv pip install \
            --python "$VENV_DIR/bin/python" \
            --no-build-isolation-package python-rtmidi \
            "textual>=0.75.0" \
            "mido>=1.3.0" \
            "python-rtmidi>=1.4.0" \
            "mingus>=0.6.1" \
            "sounddevice>=0.4.6" \
            "meson-python" \
            "numpy>=1.24.0,<2.0" \
            "scipy>=1.10.0,<1.14.0" \
            || {
                echo " ERROR: Dependency installation failed."
                exit 1
            }
        echo ""
    else
        # ── Desktop install path (Windows / macOS / x86 Linux) ────────────────
        # meson-python must be in the venv before uv sync builds python-rtmidi.
        # python-rtmidi 1.5.8 uses it as a build backend but omits it from its
        # build-system.requires; no-build-isolation-package means we can't inject
        # it via extra-build-dependencies — it must already be present.
        uv venv --seed --quiet
        "$VENV_DIR/bin/pip" install --quiet meson-python || true

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
    fi

    echo " Done."
    echo ""
else
    # .venv exists — pick up any new dependencies added since last run.
    if [[ "$_ARCH" == "armv7l" || "$_ARCH" == "aarch64" ]]; then
        # ARM: ensure pip is available (venv may have been created without --seed),
        # then use it for scipy/numpy so piwheels wheels are used, not PyPI sdists.
        uv pip install pip --python "$VENV_DIR/bin/python" --quiet || true
        # Pin numpy<2.0 and scipy<1.14: piwheels 2.x wheels require glibc 2.34
        # (Debian 12 Bookworm), but Raspbian 11 (Bullseye) only has glibc 2.31.
        "$VENV_DIR/bin/pip" install --quiet \
            --index-url https://www.piwheels.org/simple \
            --extra-index-url https://pypi.org/simple \
            "numpy>=1.24.0,<2.0" "scipy>=1.10.0,<1.14.0" || {
                echo " ERROR: scipy/numpy install from piwheels failed."
                exit 1
            }
        # Install remaining deps via uv pip. Pass the same numpy/scipy upper
        # bounds so uv accepts the piwheels wheels already in the venv and
        # does not re-resolve to a newer sdist from PyPI.
        uv pip install \
            --python "$VENV_DIR/bin/python" \
            --no-build-isolation-package python-rtmidi \
            "textual>=0.75.0" "mido>=1.3.0" "python-rtmidi>=1.4.0" \
            "mingus>=0.6.1" "sounddevice>=0.4.6" "meson-python" \
            "numpy>=1.24.0,<2.0" "scipy>=1.10.0,<1.14.0" \
            --quiet || {
                echo " ERROR: Dependency update failed."
                exit 1
            }
    else
        if ! uv sync --quiet 2>/dev/null; then
            echo ""
            echo " ERROR: Dependency sync failed."
            echo " Run manually for details:  uv sync"
            echo ""
            exit 1
        fi
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
