"""MIDI device detection and management."""
import mido
import os
import sys
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config_manager import ConfigManager


class MIDIDeviceManager:
    """Manages MIDI device enumeration and selection."""

    def __init__(self, config_manager: 'ConfigManager' = None):
        self.config_manager = config_manager
        self.selected_device: Optional[str] = None
        self.last_error: Optional[str] = None

        # Load saved device from config
        if self.config_manager:
            saved_device = self.config_manager.get_selected_device()
            if saved_device:
                # Verify device still exists
                if saved_device in self.get_input_devices():
                    self.selected_device = saved_device

    def get_input_devices(self) -> List[str]:
        """Get list of available MIDI input devices.

        Returns:
            List of MIDI input device names.
        """
        try:
            # Suppress ALSA error messages to stderr
            stderr_backup = sys.stderr
            with open(os.devnull, 'w') as devnull:
                sys.stderr = devnull
                try:
                    devices = mido.get_input_names()
                finally:
                    sys.stderr = stderr_backup

            self.last_error = None
            return devices
        except Exception as e:
            # Store user-friendly error message
            error_msg = str(e).lower()
            if "no such file" in error_msg and "snd/seq" in error_msg:
                self.last_error = "ALSA sequencer not available. Run: sudo modprobe snd-seq"
            else:
                self.last_error = f"Error: {e}"
            return []

    def select_device(self, device_name: str) -> bool:
        """Select a MIDI input device.

        Args:
            device_name: Name of the device to select.

        Returns:
            True if device is valid and selected, False otherwise.
        """
        available_devices = self.get_input_devices()
        if device_name in available_devices:
            self.selected_device = device_name
            # Save to config
            if self.config_manager:
                self.config_manager.set_selected_device(device_name)
            return True
        return False

    def get_selected_device(self) -> Optional[str]:
        """Get currently selected device name.

        Returns:
            Selected device name or None if no device selected.
        """
        return self.selected_device

    def has_devices(self) -> bool:
        """Check if any MIDI devices are available.

        Returns:
            True if at least one device is available.
        """
        return len(self.get_input_devices()) > 0
