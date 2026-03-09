# ABOUTME: FlexASIO configuration generator for low-latency shared audio.
# ABOUTME: Creates optimal TOML config matching Acordes engine (48 kHz, 1024 buffer, Float32, minimal latency).

import os
import platform
from pathlib import Path


def get_flexasio_config_path() -> Path:
    """Return the path to FlexASIO.toml in the user's AppData\Local folder (Windows only)."""
    if platform.system() != "Windows":
        return None
    appdata = os.getenv("LOCALAPPDATA")
    if not appdata:
        return None
    return Path(appdata) / "FlexASIO.toml"


def generate_flexasio_config(sample_rate: int = 48000, buffer_samples: int = 1024) -> str:
    """Generate optimal FlexASIO TOML configuration for Acordes.

    Parameters:
        sample_rate: Engine sample rate in Hz (default: 48000).
        buffer_samples: Engine buffer size in samples (default: 1024).

    Returns:
        TOML configuration as a string.

    Configuration matches Acordes engine settings:
      - Sample rate: matches engine (default 48 kHz)
      - Buffer size: matches engine (default 1024 samples)
      - Sample type: Float32 (standard for PortAudio float processing)
      - Latency: 0.0 seconds (minimal suggested latency to PortAudio)
      - Backend: Windows WASAPI shared mode (allows other apps to use audio simultaneously)
      - Input: disabled (empty device name) — Acordes is output-only
      - Output: device = "" uses system default physical output (safest, avoids wrong device names)
      - wasapiExclusiveMode = false for shared mode (the whole point of FlexASIO over raw ASIO)

    Latency calculation: buffer_samples / sample_rate
      - 1024 @ 48 kHz = 21.3 ms
      - 1024 @ 96 kHz = 10.7 ms
      - 1024 @ 44.1 kHz = 23.2 ms

    Note: device = "" in [output] means FlexASIO uses the Windows system default output device.
    This is intentional — we do not know the exact physical device name from Acordes.
    """
    latency_ms = (buffer_samples / sample_rate) * 1000
    config = f"""# FlexASIO configuration for Acordes
# Auto-generated to match Acordes audio engine settings:
# Sample rate: {sample_rate} Hz, Buffer: {buffer_samples} samples, Latency: {latency_ms:.1f} ms
# Float32, Minimal latency, WASAPI shared mode

backend = "Windows WASAPI"
bufferSizeSamples = {buffer_samples}

# Input disabled (Acordes is output-only; MIDI handled separately via python-rtmidi)
[input]
device = ""

# Output via WASAPI shared mode — allows other apps (Spotify, Firefox) to use audio simultaneously.
# device = "" selects the Windows system default output device.
[output]
device = ""
sampleType = "Float32"
suggestedLatencySeconds = 0.0
wasapiExclusiveMode = false
"""
    return config


def create_or_update_flexasio_config(sample_rate: int = 48000, buffer_samples: int = 1024) -> bool:
    """Create or update the FlexASIO.toml config file with Acordes-optimized settings.

    Parameters:
        sample_rate: Engine sample rate in Hz (default: 48000).
        buffer_samples: Engine buffer size in samples (default: 1024).

    Returns:
        True if successful, False otherwise (e.g., not on Windows, no write permissions).
    """
    config_path = get_flexasio_config_path()
    if not config_path:
        return False

    try:
        config_content = generate_flexasio_config(sample_rate=sample_rate, buffer_samples=buffer_samples)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)
        return True
    except Exception:
        return False
