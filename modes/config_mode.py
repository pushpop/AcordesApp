"""MIDI device configuration screen."""
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, ListView, ListItem, Label
from textual.binding import Binding
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from midi.device_manager import MIDIDeviceManager


class ConfigMode(Screen):
    """Screen for configuring MIDI devices."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("r", "refresh_devices", "Refresh", show=True),
        Binding("space", "select_and_close", "Select", show=True),
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

    #title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: #ffd700;
        margin-bottom: 1;
    }

    #device-list {
        width: 100%;
        height: 15;
        border: solid #ffd700;
        margin: 1 0;
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
        content-align: center middle;
        color: #00ff00;
        margin-top: 1;
    }
    """

    def __init__(self, device_manager: 'MIDIDeviceManager'):
        super().__init__()
        self.device_manager = device_manager
        self.devices = []
        self.pending_selection = None  # Track pending selection before applying

    def compose(self):
        """Compose the config mode layout."""
        yield Header()
        with Vertical(id="config-container"):
            yield Label("🎹 MIDI Device Configuration", id="title")
            yield ListView(id="device-list")
            yield Label("", id="selected-device")
            yield Label(
                "↑↓: Navigate | Space: Select & Close | R: Refresh | Esc: Close",
                id="instructions"
            )
        yield Footer()

    def on_mount(self):
        """Called when screen is mounted."""
        # Start with the currently selected device as pending
        self.pending_selection = self.device_manager.get_selected_device()
        self.refresh_device_list()

        # Set initial focus on the list
        list_view = self.query_one("#device-list", ListView)
        if self.devices:
            list_view.index = 0

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
                is_pending = device == self.pending_selection
                if is_pending:
                    list_view.append(ListItem(Label(f"☑ {device}")))
                else:
                    list_view.append(ListItem(Label(f"☐ {device}")))

        self.update_selected_display()

    def update_selected_display(self):
        """Update the selected device display."""
        selected = self.device_manager.get_selected_device()
        label = self.query_one("#selected-device", Label)

        if self.pending_selection and self.pending_selection != selected:
            label.update(f"Active: {selected or 'None'} | Pending: {self.pending_selection} (press Enter to apply)")
        elif selected:
            label.update(f"Active: {selected}")
        else:
            label.update("No device selected")

    def action_refresh_devices(self):
        """Refresh the device list."""
        self.refresh_device_list()
        self.app.notify("Device list refreshed")

    def action_select_and_close(self):
        """Select the highlighted device and close config."""
        list_view = self.query_one("#device-list", ListView)

        if list_view.index is not None and self.devices:
            if 0 <= list_view.index < len(self.devices):
                selected_device = self.devices[list_view.index]

                # Apply selection immediately
                result = self.device_manager.select_device(selected_device)
                if result:
                    self.app.notify(f"✓ Selected: {selected_device}")
                    # Close the config screen
                    self.dismiss()
                else:
                    self.app.notify(f"✗ Failed to select: {selected_device}")
