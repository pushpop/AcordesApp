"""Configuration file management."""
import json
import os
from pathlib import Path
from typing import Optional


class ConfigManager:
    """Manages application configuration."""

    def __init__(self):
        self.config_file = Path(__file__).parent / "config.json"
        self.config = self._load_config()

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
            "velocity_curve": "Linear",  # Default velocity curve type
            "last_synth_preset": None,
            "synth_state": None,
            "metronome_bpm": 120,
            "audio_device_index": None,  # PyAudio output device index (None = not yet chosen)
            "audio_device_name": None,   # Human-readable name for display
        }

    def save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    # ── MIDI device ──────────────────────────────────────────────

    def get_selected_device(self) -> Optional[str]:
        """Get the saved MIDI device."""
        return self.config.get("selected_midi_device")

    def set_selected_device(self, device_name: Optional[str]):
        """Save the selected MIDI device."""
        self.config["selected_midi_device"] = device_name
        self.save_config()

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
        """Persist current synth parameters (autosave on every change)."""
        self.config["synth_state"] = params
        self.save_config()

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

    # ── Shared BPM (Metronome ↔ Arpeggiator) ─────────────────────

    def get_bpm(self) -> int:
        """Return the shared metronome/arpeggiator BPM (default 120)."""
        return int(self.config.get("metronome_bpm", 120))

    def set_bpm(self, bpm: int):
        """Persist the BPM and save. Clamped to [50, 300]."""
        self.config["metronome_bpm"] = int(max(50, min(300, bpm)))
        self.save_config()
