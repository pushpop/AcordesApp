# ABOUTME: Configuration screen for MIDI input, audio output, and velocity curve settings.
# ABOUTME: Appears on first launch (no audio device) or when user presses C from the main app.
"""MIDI device, audio output, and velocity curve configuration screen."""
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, ListView, ListItem, Label
from textual.binding import Binding
from components.header_widget import HeaderWidget
from typing import TYPE_CHECKING, Optional, Callable, List, Tuple

if TYPE_CHECKING:
    from midi.device_manager import MIDIDeviceManager
    from config_manager import ConfigManager


class ConfigMode(Screen):
    """Screen for configuring MIDI devices, audio output, and velocity curves."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("r", "refresh_devices", "Refresh", show=True),
        Binding("space", "select_item", "Select", show=True),
        Binding("tab", "toggle_list_focus", "Switch list", show=True),
    ]

    CSS = """
    ConfigMode {
        align: center middle;
    }

    #config-container {
        width: 70;
        height: auto;
        border: thick #ffd700;
        background: #1a1a1a;
        padding: 1 2;
    }

    #device-section {
        width: 100%;
        height: auto;
    }

    #device-label {
        width: 100%;
        color: #ffd700;
        text-style: bold;
        margin-top: 1;
    }

    #device-list {
        width: 100%;
        height: 6;
        border: solid #ffd700;
        margin: 0 0 1 0;
    }

    #audio-section {
        width: 100%;
        height: auto;
    }

    #audio-label {
        width: 100%;
        color: #ffd700;
        text-style: bold;
        margin-top: 1;
    }

    #audio-list {
        width: 100%;
        height: 6;
        border: solid #ffd700;
        margin: 0 0 1 0;
    }

    #curve-section {
        width: 100%;
        height: auto;
    }

    #curve-label {
        width: 100%;
        color: #ffd700;
        text-style: bold;
        margin-top: 1;
    }

    #curve-list {
        width: 100%;
        height: 7;
        border: solid #ffd700;
        margin: 0 0 1 0;
    }

    #instructions {
        width: 100%;
        content-align: center middle;
        color: #888888;
        text-style: italic;
        margin-top: 1;
    }

    #selected-device {
        width: 100%;
        content-align: left middle;
        color: #00ff00;
        margin: 1 0 0 0;
    }

    #selected-audio {
        width: 100%;
        content-align: left middle;
        color: #00ff00;
        margin: 1 0 0 0;
    }

    #selected-curve {
        width: 100%;
        content-align: left middle;
        color: #00ff00;
        margin: 1 0 0 0;
    }
    """

    def __init__(
        self,
        device_manager: 'MIDIDeviceManager',
        config_manager: 'ConfigManager',
        on_audio_device_change: Optional[Callable[[int], None]] = None,
    ):
        super().__init__()
        self.device_manager = device_manager
        self.config_manager = config_manager
        # Callback invoked when user selects a new audio device (engine is running).
        # If None, audio selection is saved to config only (engine not yet running).
        self.on_audio_device_change = on_audio_device_change

        self.devices: List[str] = []
        self.pending_device: Optional[str] = None

        # Audio output devices: list of (index, name) tuples
        self.audio_devices: List[Tuple[int, str]] = []
        self.pending_audio_index: Optional[int] = config_manager.get_audio_device_index()

        self.velocity_curves = ["Linear", "Soft", "Normal", "Strong", "Very Strong"]
        self.pending_curve = config_manager.get_velocity_curve()

    def compose(self):
        """Compose the config mode layout."""
        yield Header()
        with Vertical(id="config-container"):
            yield HeaderWidget(title="CONFIGURATION", subtitle="MIDI, Audio Output & Velocity Curve")

            # MIDI Device Section
            with Vertical(id="device-section"):
                yield Label("MIDI INPUT DEVICE", id="device-label")
                yield ListView(id="device-list")
                yield Label("", id="selected-device")

            # Audio Output Section
            with Vertical(id="audio-section"):
                yield Label("AUDIO OUTPUT DEVICE", id="audio-label")
                yield ListView(id="audio-list")
                yield Label("", id="selected-audio")

            # Velocity Curve Section
            with Vertical(id="curve-section"):
                yield Label("VELOCITY CURVE", id="curve-label")
                yield ListView(id="curve-list")
                yield Label("", id="selected-curve")

            yield Label(
                "Tab: Switch section | ↑↓: Navigate | Space: Select | R: Refresh | Esc: Close",
                id="instructions"
            )
        yield Footer()

    def on_mount(self):
        """Called when screen is mounted."""
        self.pending_device = self.device_manager.get_selected_device()
        self.refresh_device_list()
        self.refresh_audio_list()
        self.refresh_curve_list()

        # Start focus on MIDI device list
        device_list = self.query_one("#device-list", ListView)
        if self.devices:
            device_list.index = 0
        device_list.focus()

    def refresh_device_list(self):
        """Refresh the list of MIDI input devices.

        Prepends sentinel option to allow proceeding without MIDI device selection.
        """
        list_view = self.query_one("#device-list", ListView)
        list_view.clear()

        self.devices = self.device_manager.get_input_devices()

        # Always prepend "No MIDI Device" option (None sentinel)
        marker = "☑" if self.pending_device is None else "☐"
        list_view.append(ListItem(Label(f"{marker} No MIDI Device")))

        if not self.devices:
            if self.device_manager.last_error:
                list_view.append(ListItem(Label("❌ " + self.device_manager.last_error)))
            else:
                list_view.append(ListItem(Label("(No devices found)")))
        else:
            for device in self.devices:
                marker = "☑" if device == self.pending_device else "☐"
                list_view.append(ListItem(Label(f"{marker} {device}")))

        self._update_device_label()

    def refresh_audio_list(self):
        """Refresh the list of PyAudio output devices.

        Sentinel values prepended to the list:
          -2 = System Default (OS/PipeWire routes to active speakers — recommended on Linux)
          -1 = No Audio (engine runs silently; useful for browsing compendium, etc.)
        """
        from music.synth_engine import list_output_devices
        list_view = self.query_one("#audio-list", ListView)
        list_view.clear()

        hardware = list_output_devices()
        # Prepend special entries so they are always available regardless of hardware
        self.audio_devices = [(-2, "System Default"), (-1, "No Audio")] + hardware

        for idx, name in self.audio_devices:
            marker = "☑" if idx == self.pending_audio_index else "☐"
            list_view.append(ListItem(Label(f"{marker} {name}")))

        self._update_audio_label()

    def refresh_curve_list(self):
        """Refresh the velocity curve list."""
        list_view = self.query_one("#curve-list", ListView)
        list_view.clear()

        for curve in self.velocity_curves:
            marker = "☑" if curve == self.pending_curve else "☐"
            list_view.append(ListItem(Label(f"{marker} {curve}")))

        self._update_curve_label()

    def _update_device_label(self):
        """Update the MIDI device status label."""
        label = self.query_one("#selected-device", Label)
        active = self.device_manager.get_selected_device()
        if self.pending_device and self.pending_device != active:
            label.update(f"Active: {active or 'None'} | Pending: {self.pending_device}")
        elif active:
            label.update(f"Active: {active}")
        else:
            label.update("No device selected")

    def _update_audio_label(self):
        """Update the audio output device status label."""
        label = self.query_one("#selected-audio", Label)
        if self.pending_audio_index is not None:
            name = next((n for i, n in self.audio_devices if i == self.pending_audio_index),
                        self.config_manager.get_audio_device_name() or "Unknown")
            label.update(f"Selected: {name}")
        else:
            label.update("No audio device selected")

    def _update_curve_label(self):
        """Update the velocity curve status label."""
        label = self.query_one("#selected-curve", Label)
        label.update(f"Selected: {self.pending_curve}")

    def action_refresh_devices(self):
        """Refresh all device lists."""
        self.refresh_device_list()
        self.refresh_audio_list()

    def _focused_list_id(self) -> str:
        """Return the ID of whichever list currently has focus."""
        for list_id in ("#device-list", "#audio-list", "#curve-list"):
            lv = self.query_one(list_id, ListView)
            if self.focused is lv:
                return list_id
        return "#device-list"

    def action_toggle_list_focus(self):
        """Tab — cycle focus: device → audio → curve → device."""
        current = self._focused_list_id()

        if current == "#device-list":
            next_id = "#audio-list"
            # Auto-highlight current audio selection (includes sentinel entries -2 and -1)
            if self.pending_audio_index is not None:
                indices = [i for i, _ in self.audio_devices]
                if self.pending_audio_index in indices:
                    self.query_one("#audio-list", ListView).index = indices.index(self.pending_audio_index)
        elif current == "#audio-list":
            next_id = "#curve-list"
            # Auto-highlight current curve selection
            if self.pending_curve in self.velocity_curves:
                self.query_one("#curve-list", ListView).index = self.velocity_curves.index(self.pending_curve)
        else:
            next_id = "#device-list"
            # Auto-highlight current MIDI selection
            # Index 0 is "No MIDI Device" (None), indices 1+ are hardware devices
            if self.pending_device is None:
                self.query_one("#device-list", ListView).index = 0
            elif self.pending_device in self.devices:
                self.query_one("#device-list", ListView).index = self.devices.index(self.pending_device) + 1

        self.query_one(next_id, ListView).focus()

    def action_select_item(self):
        """Space — select highlighted item in the focused list."""
        current = self._focused_list_id()
        if current == "#curve-list":
            self._select_curve()
        elif current == "#audio-list":
            self._select_audio_device()
        else:
            self._select_device()

    def _select_device(self):
        """Apply the highlighted MIDI device.

        Index 0 is the "No MIDI Device" sentinel (None).
        Indices 1+ are actual hardware devices.
        """
        list_view = self.query_one("#device-list", ListView)
        if list_view.index is None:
            return

        if list_view.index == 0:
            # "No MIDI Device" selected
            self.pending_device = None
            self.device_manager.select_device(None)
        elif 1 <= list_view.index <= len(self.devices):
            # Hardware device selected (offset by 1 due to sentinel)
            selected = self.devices[list_view.index - 1]
            self.pending_device = selected
            self.device_manager.select_device(selected)

        self.refresh_device_list()

    def _select_audio_device(self):
        """Save the highlighted audio output device and optionally restart the engine."""
        list_view = self.query_one("#audio-list", ListView)
        if list_view.index is None or not self.audio_devices:
            return
        if not (0 <= list_view.index < len(self.audio_devices)):
            return

        idx, name = self.audio_devices[list_view.index]
        self.pending_audio_index = idx
        self.config_manager.set_audio_device(idx, name)
        self.refresh_audio_list()

        # If the engine is already running, trigger a restart with the new device
        if self.on_audio_device_change is not None:
            self.on_audio_device_change(idx)

    def _select_curve(self):
        """Apply the highlighted velocity curve."""
        list_view = self.query_one("#curve-list", ListView)
        if list_view.index is not None and 0 <= list_view.index < len(self.velocity_curves):
            selected = self.velocity_curves[list_view.index]
            self.pending_curve = selected
            self.config_manager.set_velocity_curve(selected)
            self.refresh_curve_list()
