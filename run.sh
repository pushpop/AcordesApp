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

# Spinner utility: runs in the foreground while a background job ($1) is alive.
# Prints a rotating character beside a message, then a check mark when done.
# Usage: _spin $PID "message"
_spin() {
    local _pid=$1 _msg=$2
    local _chars='|/-\' _i=0
    while kill -0 "$_pid" 2>/dev/null; do
        printf "\r  %s  %s" "${_chars:$((_i % 4)):1}" "$_msg"
        sleep 0.1
        _i=$((_i + 1))
    done
    printf "\r  \u2714  %s\n" "$_msg"
}

if [[ "$_ARCH" == "armv7l" || "$_ARCH" == "aarch64" ]]; then
    echo ""
    echo "  +---------------------------+"
    echo "  |   A C O R D E S  - ARM   |"
    echo "  +---------------------------+"
    echo ""

    if command -v apt-get &>/dev/null; then
        if ! dpkg -l libasound2-dev &>/dev/null 2>&1 | grep -q "^ii"; then
            echo "  Installing system build dependencies..."
            sudo apt-get install -y \
                libasound2-dev libjack-jackd2-dev ninja-build libffi-dev \
                gfortran python3-dev \
                libopenblas0 \
                >/dev/null 2>&1 || true
            printf "  \u2714  System dependencies ready\n"
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

    # 4. Allow the RT scheduler to run indefinitely (kernel default caps RT tasks
    #    at 95% of wall-clock time to prevent lockups). Patchbox sets this to -1
    #    (unlimited) so the audio callback is never throttled mid-buffer.
    sudo sysctl -q kernel.sched_rt_runtime_us=-1 2>/dev/null || true

    # 5. Kill PulseAudio completely for this session.
    #    PulseAudio inserts itself as the ALSA default device and adds its own
    #    resampler + jitter buffer; this causes severe audio artifacts and
    #    prevents PortAudio from opening the bcm2835 hardware directly.
    #    pactl suspend only pauses sinks but leaves PA running and able to
    #    reclaim the device. pulseaudio --kill terminates it outright.
    #    Masking the socket stops auto-respawn for the rest of this session.
    if command -v pulseaudio &>/dev/null; then
        pulseaudio --kill 2>/dev/null || true
        systemctl --user stop  pulseaudio.socket pulseaudio.service 2>/dev/null || true
        systemctl --user mask  pulseaudio.socket pulseaudio.service 2>/dev/null || true
        # Wait briefly to ensure PA has released the ALSA device before we open it.
        sleep 0.5
    fi

    # 6. Detect bcm2835 headphone card index and write ~/.asoundrc so that
    #    the ALSA "default" PCM points directly at the hardware device.
    #    This is rewritten on every launch so a stale file cannot cause problems.
    _HEADPHONE_CARD=$(aplay -l 2>/dev/null \
        | grep -i "bcm2835 Headphones" \
        | head -1 \
        | sed 's/card \([0-9]*\):.*/\1/')
    # Fallback: if not found by name, use card 1 (typical Pi 4 layout).
    _HEADPHONE_CARD="${_HEADPHONE_CARD:-1}"
    _ASOUNDRC="$HOME/.asoundrc"
    cat > "$_ASOUNDRC" <<ASOUNDRC
# Acordes ALSA config - auto-generated each launch by run.sh
# Routes default PCM directly to the bcm2835 headphone jack (card ${_HEADPHONE_CARD})
# bypassing dmix and PulseAudio.  Run run.sh again to regenerate.
pcm.!default {
    type plug
    slave.pcm "hw:${_HEADPHONE_CARD},0"
}
ctl.!default {
    type hw
    card ${_HEADPHONE_CARD}
}
ASOUNDRC
    echo " ALSA default -> bcm2835 headphone jack (card ${_HEADPHONE_CARD})"

    # 7. Move USB and Ethernet IRQs off CPU0 so they do not compete with the
    #    audio DMA interrupt.  Pi 4 DWC2/xhci IRQs default to CPU0.
    #    IRQ numbers vary per kernel; find them by subsystem name.
    for _irq_name in xhci_hcd dwc2 smsc95xx eth0; do
        _irq_num=$(grep -r "$_irq_name" /proc/irq/*/node 2>/dev/null | head -1 | cut -d/ -f4)
        if [[ -n "$_irq_num" && -f "/proc/irq/$_irq_num/smp_affinity_list" ]]; then
            echo 1 | sudo tee "/proc/irq/$_irq_num/smp_affinity_list" \
                >/dev/null 2>&1 || true
        fi
    done
fi

# ── 4. Pin Python version — install automatically if missing ──────────────────
# On ARM (armv7l/aarch64) with Raspbian 11 (Bullseye, glibc 2.31) we use
# Python 3.9 because piwheels cp39 wheels were built on Bullseye and work
# with glibc 2.31. piwheels cp311 wheels were built on Bookworm (glibc 2.34)
# and fail at import on Bullseye regardless of numpy version.
# On desktop (x86/aarch64 Bookworm) we prefer 3.12, falling back to 3.11.
if [[ "$_ARCH" == "armv7l" ]]; then
    _PY_PRIMARY="3.9"
    _PY_FALLBACK="3.11"
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

        # Pin numpy<2.0 and scipy<1.14: piwheels 2.x wheels require glibc 2.34
        # (Debian 12 Bookworm), but Raspbian 11 (Bullseye) only has glibc 2.31.
        # numpy 1.26.4 and scipy 1.13.x are the last releases built for glibc 2.31.
        "$VENV_DIR/bin/pip" install --quiet \
            --index-url https://www.piwheels.org/simple \
            --extra-index-url https://pypi.org/simple \
            "numpy>=1.24.0,<2.0" "scipy>=1.10.0,<1.14.0" &
        _PIP_PID=$!
        _spin $_PIP_PID "Installing numpy / scipy  (piwheels)"
        wait $_PIP_PID || { echo "  ERROR: scipy/numpy install failed."; exit 1; }

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
            "evdev>=1.6.0" \
            "numpy>=1.24.0,<2.0" \
            "scipy>=1.10.0,<1.14.0" \
            --quiet &
        _UV_PID=$!
        _spin $_UV_PID "Installing remaining dependencies"
        wait $_UV_PID || { echo "  ERROR: Dependency installation failed."; exit 1; }
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
            "numpy>=1.24.0,<2.0" "scipy>=1.10.0,<1.14.0" &
        _PIP_PID=$!
        _spin $_PIP_PID "Checking numpy / scipy  (piwheels)"
        wait $_PIP_PID || { echo "  ERROR: scipy/numpy update failed."; exit 1; }
        # Install remaining deps via uv pip. Pass the same numpy/scipy upper
        # bounds so uv accepts the piwheels wheels already in the venv and
        # does not re-resolve to a newer sdist from PyPI.
        uv pip install \
            --python "$VENV_DIR/bin/python" \
            --no-build-isolation-package python-rtmidi \
            "textual>=0.75.0" "mido>=1.3.0" "python-rtmidi>=1.4.0" \
            "mingus>=0.6.1" "sounddevice>=0.4.6" "meson-python" "evdev>=1.6.0" \
            "numpy>=1.24.0,<2.0" "scipy>=1.10.0,<1.14.0" \
            --quiet &
        _UV_PID=$!
        _spin $_UV_PID "Checking remaining dependencies"
        wait $_UV_PID || { echo "  ERROR: Dependency update failed."; exit 1; }
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

# ── 7. Color system + SSH responsiveness ──────────────────────────────────────
# Textual detects terminal color depth from COLORTERM and terminfo. On ARM the
# detection often falls back to 16-color mode (ANSI colors 0-15), which maps
# our hex palette to the terminal's own theme colors — producing wrong hues.
#
# Color fix per terminal type:
#   SSH sessions   : 256-color mode. Truecolor escape codes are ~16 bytes per
#                    color vs ~8 bytes for 256-color, doubling the render bytes
#                    sent over the wire per frame. 256-color is visually
#                    indistinguishable on the Pi palette and halves SSH traffic.
#   Framebuffer TTY: 256-color. Raw kernel/TFT framebuffer consoles cannot
#                    render 24-bit color but do honor xterm-256 escape codes.
#
# SSH responsiveness: cap Textual's frame rate to 30 fps over SSH. The default
# 60 fps sends twice as many render frames per second over the network; 30 fps
# is imperceptible on a TUI and halves the ongoing SSH bandwidth.
#
# Desktop builds leave these unset so Textual auto-detects normally.
if [[ "$_ARCH" == "armv7l" || "$_ARCH" == "aarch64" ]]; then
    if [[ -n "$SSH_CONNECTION" || -n "$SSH_CLIENT" || -n "$SSH_TTY" ]]; then
        export TEXTUAL_COLOR_SYSTEM=256
        export TEXTUAL_FPS=30
    elif [[ "$(tty 2>/dev/null)" == /dev/tty* ]]; then
        export TEXTUAL_COLOR_SYSTEM=256
    fi
    # Disable all Textual internal animations (scrolling, focus transitions, etc.)
    # on ARM. Each animation frame drives a timer wakeup that competes with the
    # audio callback for the GIL, adding latency and xrun risk on the Pi 4.
    export TEXTUAL_ANIMATIONS=none
fi

# ── 8. Launch ──────────────────────────────────────────────────────────────────
# The audio callback promotes itself to SCHED_FIFO real-time scheduling
# inside synth_engine._elevate_audio_priority() — no process-level nice
# adjustment needed here (and negative nice requires root on Linux).
if [[ "$_ARCH" == "armv7l" || "$_ARCH" == "aarch64" ]]; then
    echo ""
    printf "  \u25B6  Launching Acordes...\n"
    echo ""
fi
uv run python "$SCRIPT_DIR/main.py"
