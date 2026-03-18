#!/usr/bin/env bash
# ABOUTME: OStra ARM launcher - sets up audio, CPU, display before starting Acordes.
# ABOUTME: Replaces run.sh for boot use on Raspberry Pi 4B.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Terminal font for correct Textual UI rendering on TFT-LCD console
setfont Lat15-TerminusBold14.psf.gz 2>/dev/null || true

# Textual render rate: Pi 4B can handle 60 FPS for TUI without audio impact.
# Higher FPS = more responsive UI updates when navigating and changing focus.
export TEXTUAL_FPS=60

# 256-color terminal for Textual
export TERM=xterm-256color

# CPU performance governor for low-latency audio
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null 2>&1 || true

# Real-time scheduling limits
sudo sh -c 'echo @audio - rtprio 95 >> /etc/security/limits.conf' 2>/dev/null || true
sudo sh -c 'echo @audio - memlock unlimited >> /etc/security/limits.conf' 2>/dev/null || true

# VM tuning for audio stability and SD card write stall reduction
sudo sysctl -w vm.swappiness=10 > /dev/null 2>&1 || true
# dirty_ratio/dirty_background_ratio: limit kernel dirty-page accumulation so
# SD card flush bursts are smaller and shorter, reducing UI event loop stalls.
sudo sysctl -w vm.dirty_ratio=10 > /dev/null 2>&1 || true
sudo sysctl -w vm.dirty_background_ratio=5 > /dev/null 2>&1 || true
# min_free_kbytes: keep 32MB permanently free to avoid sudden allocation stalls.
sudo sysctl -w vm.min_free_kbytes=32768 > /dev/null 2>&1 || true

# NOTE: Scheduler tuning for uvloop (kernel.sched_rt_runtime_us, timer_migration,
# sched_min_granularity_ns, sched_wakeup_granularity_ns) is applied via
# /etc/sysctl.d/99-acordes-rt.conf at boot by systemd-sysctl.service.
# Do NOT add them here - sudo sysctl at autologin time can block on a
# password prompt and prevent auto-launch.

# Kill PulseAudio if running (conflicts with ALSA direct access)
pulseaudio --kill 2>/dev/null || true

# Route ALSA to bcm2835 headphone jack (card 0)
export ALSA_CARD=0

# Set audio IRQ affinity to CPU core 3 (isolated from UI thread on core 0)
AUDIO_IRQ=$(grep -i "bcm2835" /proc/interrupts 2>/dev/null | awk -F: '{print $1}' | tr -d ' ' | head -1)
if [ -n "$AUDIO_IRQ" ]; then
    echo 8 | sudo tee /proc/irq/$AUDIO_IRQ/smp_affinity > /dev/null 2>&1 || true
fi

# Xbox controller USB power cycle.
# After a Pi reboot the controller enters pairing/search mode (blinking light)
# because the reboot cuts USB power mid-session. A driver unbind/rebind is not
# enough - the device needs a full USB power cycle (deauthorize then reauthorize)
# to re-enumerate cleanly and complete the xpad GIP handshake.
# This is equivalent to physically unplugging and replugging the USB cable.
_xbox_power_cycle() {
    local vendor_id="045e"  # Microsoft
    local dev_dir=""

    # Find the Microsoft USB device in sysfs
    for f in /sys/bus/usb/devices/*/idVendor; do
        if [ "$(cat "$f" 2>/dev/null)" = "$vendor_id" ]; then
            dev_dir="$(dirname "$f")"
            break
        fi
    done
    [ -z "$dev_dir" ] && return  # No Microsoft USB device found

    local auth_file="$dev_dir/authorized"
    [ -f "$auth_file" ] || return  # No authorized control available

    # Deauthorize (USB disconnect), pause, reauthorize (USB reconnect).
    # This causes the controller to fully re-enumerate and xpad to perform
    # a fresh GIP initialization handshake, exiting pairing/search mode.
    echo 0 | sudo tee "$auth_file" > /dev/null 2>&1 || return
    sleep 1
    echo 1 | sudo tee "$auth_file" > /dev/null 2>&1 || true
    sleep 3  # Wait for re-enumeration and xpad handshake to complete
}
_xbox_power_cycle

# Draw OStra splash on TFT-LCD
/usr/local/bin/ostra-splash 2>/dev/null || true

# Prevent multiple instances.
# Use absolute path for main.py - when auto-launched from .bash_profile the
# working directory is /home/push, not /home/push/Acordes.
#
# NOTE: Do NOT use taskset -c 3 here.
# taskset pins the entire process tree including the SynthEngine subprocess.
# The audio callback thread (SCHED_FIFO) and the Textual UI asyncio thread
# would then both compete for CPU3, causing the RT thread to starve the UI.
# The audio callback already has SCHED_FIFO priority (set in synth_engine.py)
# which gives it preemption over the UI thread without needing CPU isolation.
# CPUs 0-2 handle everything; isolcpus=3 in cmdline.txt is available for
# future per-thread affinity pinning if needed.

# Pygame display settings for the ARM Pygame UI.
# SDL_VIDEODRIVER=offscreen: pygame renders to an offscreen surface; frames
#   are written directly to /dev/fb0 by Fb0Writer (scales 480x320 -> 790x600).
#   This works on tty, over SSH, and without X11 or a KMS/DRM driver.
# SDL_FBDEV/SDL_FBACCEL: retained for compatibility; unused by offscreen driver.
# PYGAME_HIDE_SUPPORT_PROMPT: suppress pygame startup banner in console output.
export SDL_VIDEODRIVER=offscreen
export SDL_FBDEV=/dev/fb0
export SDL_FBACCEL=0
export PYGAME_HIDE_SUPPORT_PROMPT=1

exec flock -n /tmp/acordes.lock "$VENV_DIR/bin/python" "$SCRIPT_DIR/main.py"
