"""MIDI device configuration screen."""
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, ListView, ListItem, Label
from textual.binding import Binding
from components.header_widget import HeaderWidget
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from midi.device_manager import MIDIDeviceManager
    from config_manager import ConfigManager


class ConfigMode(Screen):
    """Screen for configuring MIDI devices and velocity curves."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("r", "refresh_devices", "Refresh", show=True),
        Binding("space", "select_item", "Select", show=True),
        Binding("tab", "focus_next_section", "Next section", show=True),
        Binding("shift+tab", "focus_prev_section", "Prev section", show=False),
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
        height: 8;
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

    #selected-curve {
        width: 100%;
        content-align: left middle;
        color: #00ff00;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, device_manager: 'MIDIDeviceManager', config_manager: 'ConfigManager'):
        super().__init__()
        self.device_manager = device_manager
        self.config_manager = config_manager
        self.devices = []
        self.pending_device = None  # Track pending device selection before applying

        # Velocity curves: 5 curve types (data will be defined later)
        self.velocity_curves = [
            "Linear",
            "Soft",
            "Normal",
            "Strong",
            "Very Strong"
        ]
        # Load saved velocity curve, or default to Linear
        self.pending_curve = config_manager.get_velocity_curve()

    def compose(self):
        """Compose the config mode layout."""
        yield Header()
        with Vertical(id="config-container"):
            yield HeaderWidget(title="MIDI CONFIGURATION", subtitle="Device & Velocity Curve")

            # MIDI Device Section
            with Vertical(id="device-section"):
                yield Label("MIDI INPUT DEVICE", id="device-label")
                yield ListView(id="device-list")
                yield Label("", id="selected-device")

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
        # Initialize device list
        self.pending_device = self.device_manager.get_selected_device()
        self.refresh_device_list()

        # Initialize velocity curve list
        self.refresh_curve_list()

        # Set initial focus on device list
        device_list = self.query_one("#device-list", ListView)
        if self.devices:
            device_list.index = 0
        device_list.focus()

    def refresh_device_list(self):
        """Refresh the list of MIDI devices."""
        list_view = self.query_one("#device-list", ListView)
        list_view.clear()

        self.devices = self.device_manager.get_input_devices()

        if not self.devices:
            # Show helpful error message if available
            if self.device_manager.last_error:
                list_view.append(ListItem(Label("❌ " + self.device_manager.last_error)))
            else:
                list_view.append(ListItem(Label("No MIDI devices found")))
        else:
            for device in self.devices:
                is_pending = device == self.pending_device
                if is_pending:
                    list_view.append(ListItem(Label(f"☑ {device}")))
                else:
                    list_view.append(ListItem(Label(f"☐ {device}")))

        self.update_selected_display()

    def refresh_curve_list(self):
        """Refresh the list of velocity curves."""
        list_view = self.query_one("#curve-list", ListView)
        list_view.clear()

        for curve in self.velocity_curves:
            is_pending = curve == self.pending_curve
            if is_pending:
                list_view.append(ListItem(Label(f"☑ {curve}")))
            else:
                list_view.append(ListItem(Label(f"☐ {curve}")))

        self.update_selected_display()

    def update_selected_display(self):
        """Update the selected device and curve displays."""
        selected_device = self.device_manager.get_selected_device()
        device_label = self.query_one("#selected-device", Label)

        if self.pending_device and self.pending_device != selected_device:
            device_label.update(f"Active: {selected_device or 'None'} | Pending: {self.pending_device}")
        elif selected_device:
            device_label.update(f"Active: {selected_device}")
        else:
            device_label.update("No device selected")

        # Update velocity curve display
        curve_label = self.query_one("#selected-curve", Label)
        curve_label.update(f"Selected: {self.pending_curve}")

    def action_refresh_devices(self):
        """Refresh the device list."""
        self.refresh_device_list()
        self.app.notify("Device list refreshed")

    def _curve_list_is_focused(self) -> bool:
        """Return True if the velocity curve list currently has Textual focus."""
        return self.focused is self.query_one("#curve-list", ListView)

    def action_focus_next_section(self):
        """Tab — move focus from device list to curve list."""
        curve_list = self.query_one("#curve-list", ListView)
        curve_list.focus()

    def action_focus_prev_section(self):
        """Shift+Tab — move focus from curve list back to device list."""
        device_list = self.query_one("#device-list", ListView)
        device_list.focus()

    def action_select_item(self):
        """Space — select highlighted item in whichever list currently has focus."""
        if self._curve_list_is_focused():
            self._select_curve()
        else:
            self._select_device()

    def _select_device(self):
        """Select the highlighted device."""
        list_view = self.query_one("#device-list", ListView)

        if list_view.index is not None and self.devices:
            if 0 <= list_view.index < len(self.devices):
                selected_device = self.devices[list_view.index]
                self.pending_device = selected_device

                # Apply selection
                result = self.device_manager.select_device(selected_device)
                if result:
                    self.app.notify(f"✓ Device: {selected_device}")
                    self.refresh_device_list()
                else:
                    self.app.notify(f"✗ Failed to select: {selected_device}")

    def _select_curve(self):
        """Select the highlighted velocity curve."""
        list_view = self.query_one("#curve-list", ListView)

        if list_view.index is not None:
            if 0 <= list_view.index < len(self.velocity_curves):
                selected_curve = self.velocity_curves[list_view.index]
                self.pending_curve = selected_curve

                # Save to config_manager
                self.config_manager.set_velocity_curve(selected_curve)
                self.app.notify(f"✓ Curve: {selected_curve}")
                self.refresh_curve_list()
