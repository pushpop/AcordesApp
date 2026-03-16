"""Configuration file management."""
import copy
import json
import os
import platform
import sys
import threading
from pathlib import Path
from typing import Optional

# Audio backends that only exist on Windows. If a config.json saved on Windows
# is loaded on Linux/macOS (e.g. after copying Acordes to a Raspberry Pi),
# these values are treated as unconfigured so the platform picks a sane default.
_WINDOWS_ONLY_BACKENDS = {"ASIO", "WASAPI", "DirectSound"}


class ConfigManager:
    """Manages application configuration."""

    # Seconds to wait after the last high-frequency change before writing to disk.
    _DEBOUNCE_SECONDS = 2.0

    def __init__(self):
        self.config_file = Path(__file__).parent / "config.json"
        self.config = self._load_config()
        self._save_timer: Optional[threading.Timer] = None
        self._timer_lock = threading.Lock()

    def _load_config(self) -> dict:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return self._default_config()
        return self._default_config()

    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            "selected_midi_device": None,
            "midi_device_configured": False,  # True after user makes first choice
            "velocity_curve": "Linear",  # Default velocity curve type
            "last_synth_preset": None,
            "synth_state": None,
            "metronome_bpm": 120,
            "audio_device_index": None,   # sounddevice output device index (None = not yet chosen)
            "audio_device_name": None,    # Human-readable name for display
            "audio_backend": None,        # Host API name filter (None = not yet chosen)
            "buffer_size": 2048 if platform.machine() in ("armv7l", "aarch64") else 1024,  # Audio buffer size in samples
        }

    def _flush_to_disk(self):
        """Write a snapshot of config to disk. Safe to call from any thread."""
        with self._timer_lock:
            self._save_timer = None
        try:
            snapshot = copy.deepcopy(self.config)
            with open(self.config_file, 'w') as f:
                json.dump(snapshot, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def _schedule_save(self):
        """Defer a write to disk. Resets the timer on each call (debounce).

        Use for high-frequency setters (synth_state, bpm) to avoid SD card
        storms. The write happens _DEBOUNCE_SECONDS after the last call.
        """
        with self._timer_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(self._DEBOUNCE_SECONDS, self._flush_to_disk)
            self._save_timer.daemon = True
            self._save_timer.start()

    def save_config(self):
        """Immediately flush config to disk. Use for critical one-off writes."""
        with self._timer_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
        self._flush_to_disk()

    def flush(self):
        """Force any pending deferred save to disk. Call on clean app exit."""
        self.save_config()

    # ── MIDI device ──────────────────────────────────────────────

    def get_selected_device(self) -> Optional[str]:
        """Get the saved MIDI device."""
        return self.config.get("selected_midi_device")

    def set_selected_device(self, device_name: Optional[str]):
        """Save the selected MIDI device."""
        self.config["selected_midi_device"] = device_name
        self.config["midi_device_configured"] = True
        self.save_config()

    def is_midi_device_configured(self) -> bool:
        """Check if user has made a MIDI device choice (including 'No MIDI Device')."""
        return self.config.get("midi_device_configured", False)

    # ── Velocity curve ───────────────────────────────────────────

    def get_velocity_curve(self) -> str:
        """Get the saved velocity curve type (default: 'Linear')."""
        return self.config.get("velocity_curve", "Linear")

    def set_velocity_curve(self, curve_name: str):
        """Save the selected velocity curve type."""
        self.config["velocity_curve"] = curve_name
        self.save_config()

    # ── Synth preset persistence ─────────────────────────────────

    def get_last_preset(self) -> Optional[str]:
        """Return the filename of the last active preset, or None."""
        return self.config.get("last_synth_preset")

    def set_last_preset(self, filename: Optional[str]):
        """Persist the filename of the currently active preset."""
        self.config["last_synth_preset"] = filename
        self.save_config()

    def get_synth_state(self) -> Optional[dict]:
        """Return the last auto-saved synth parameter state, or None."""
        return self.config.get("synth_state")

    def set_synth_state(self, params: dict):
        """Persist current synth parameters (autosave on every change).

        Uses a debounced write so rapid CC knob sweeps produce a single SD
        write rather than one per callback tick.
        """
        self.config["synth_state"] = params
        self._schedule_save()

    # ── Audio output device ───────────────────────────────────────

    def get_audio_device_index(self) -> Optional[int]:
        """Get the saved PyAudio output device index (None = not yet chosen)."""
        return self.config.get("audio_device_index")

    def set_audio_device(self, index: Optional[int], name: Optional[str]):
        """Save the selected audio output device index and display name."""
        self.config["audio_device_index"] = index
        self.config["audio_device_name"] = name
        self.save_config()

    def get_audio_device_name(self) -> Optional[str]:
        """Get the saved audio output device display name."""
        return self.config.get("audio_device_name")

    def get_audio_backend(self) -> Optional[str]:
        """Get the saved audio backend/host API name (None = not yet chosen).

        Windows-only backends are ignored on non-Windows platforms so a config
        saved on Windows works cleanly when moved to a Raspberry Pi or Mac.
        """
        backend = self.config.get("audio_backend")
        if sys.platform != "win32" and backend in _WINDOWS_ONLY_BACKENDS:
            return None
        return backend

    def set_audio_backend(self, backend_name: Optional[str]):
        """Save the selected audio backend/host API name."""
        self.config["audio_backend"] = backend_name
        self.save_config()

    # ── Buffer size ───────────────────────────────────────────────

    def get_buffer_size(self) -> int:
        """Get the saved audio buffer size in samples (default: 1024 desktop, 2048 ARM).

        On ARM, values below 2048 are migrated up to 2048 on first read to
        match the engine floor and avoid showing a stale config screen selection.
        """
        size = int(self.config.get("buffer_size", 1024))
        if platform.machine() in ("armv7l", "aarch64") and size < 2048:
            size = 2048
            self.config["buffer_size"] = size
            self.save_config()
        return size

    def set_buffer_size(self, size: int):
        """Save the selected audio buffer size in samples."""
        self.config["buffer_size"] = int(size)
        self.save_config()

    # ── Shared BPM (Metronome ↔ Arpeggiator) ─────────────────────

    def get_bpm(self) -> int:
        """Return the shared metronome/arpeggiator BPM (default 120)."""
        return int(self.config.get("metronome_bpm", 120))

    def set_bpm(self, bpm: int):
        """Persist the BPM. Clamped to [50, 300]. Uses debounced write."""
        self.config["metronome_bpm"] = int(max(50, min(300, bpm)))
        self._schedule_save()
