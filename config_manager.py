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
            "selected_midi_device": None
        }

    def save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_selected_device(self) -> Optional[str]:
        """Get the saved MIDI device."""
        return self.config.get("selected_midi_device")

    def set_selected_device(self, device_name: Optional[str]):
        """Save the selected MIDI device."""
        self.config["selected_midi_device"] = device_name
        self.save_config()
