#!/usr/bin/env python3
"""MIDI Piano TUI Application - Main Entry Point."""
import os
import sys

# Note: On Windows, mido will auto-detect available MIDI backends
# We don't force a specific backend to avoid DLL issues

from textual.app import App
from textual.binding import Binding
from textual.widgets import Static, Header, Footer
from textual.containers import Vertical, Container
from textual.screen import Screen

from config_manager import ConfigManager
from midi.device_manager import MIDIDeviceManager
from midi.input_handler import MIDIInputHandler
from music.chord_detector import ChordDetector
from music.chord_library import ChordLibrary

from modes.config_mode import ConfigMode
from modes.piano_mode import PianoMode
from modes.compendium_mode import CompendiumMode
from modes.synth_mode import SynthMode
from components.confirmation_dialog import ConfirmationDialog


class MainScreen(Screen):
    """Main screen with split layout."""

    CSS = """
    MainScreen {
        layout: vertical;
    }

    #content-area {
        height: 100%;
        width: 100%;
        align: left top;
    }
    """

    BINDINGS = [
        Binding("1", "show_piano", "Piano", show=True),
        Binding("2", "show_compendium", "Compendium", show=True),
        Binding("3", "show_synth", "Synth", show=True),
        Binding("c", "show_config", "Config", show=True),
        Binding("escape", "quit_app", "Quit", show=True),
    ]

    def __init__(self, app_context):
        super().__init__()
        self.app_context = app_context

    def compose(self):
        """Compose the main screen layout."""
        yield Header()

        # Content area for Piano or Compendium - NO CONTAINER
        with Container(id="content-area"):
            pass

        yield Footer()

    def on_mount(self):
        """Called when mounted."""
        # Show initial mode
        self.action_show_piano()

    def action_show_piano(self):
        """Show piano mode."""
        content = self.query_one("#content-area")
        content.remove_children()

        piano = self.app_context["create_piano"]()
        content.mount(piano)
        self.app_context["current_mode"] = "piano"

    def action_show_compendium(self):
        """Show compendium mode."""
        content = self.query_one("#content-area")
        content.remove_children()

        compendium = self.app_context["create_compendium"]()
        content.mount(compendium)
        self.app_context["current_mode"] = "compendium"

    def action_show_synth(self):
        """Show synth mode."""
        content = self.query_one("#content-area")
        content.remove_children()

        synth = self.app_context["create_synth"]()
        content.mount(synth)
        self.app_context["current_mode"] = "synth"

    def action_show_config(self):
        """Show config modal."""
        # Remember current mode
        self.app_context["mode_before_config"] = self.app_context["current_mode"]

        def on_closed(result):
            # Update footer
            self.app.update_sub_title()

            # Reopen MIDI device
            selected = self.app_context["device_manager"].get_selected_device()
            if selected:
                self.app_context["midi_handler"].close_device()
                self.app_context["midi_handler"].open_device(selected)

            # Return to previous mode
            if self.app_context["mode_before_config"] == "piano":
                self.action_show_piano()
            elif self.app_context["mode_before_config"] == "compendium":
                self.action_show_compendium()
            else:
                self.action_show_synth()

        config = ConfigMode(self.app_context["device_manager"])
        self.app.push_screen(config, on_closed)

    def action_quit_app(self):
        """Quit with confirmation."""
        def check_quit(result):
            if result:
                self.app.exit()

        self.app.push_screen(ConfirmationDialog("Quit Acordes?"), check_quit)


class AcordesApp(App):
    """MIDI Piano TUI Application."""

    CSS = """
    """

    def __init__(self):
        super().__init__()
        # Initialize config and components
        self.config_manager = ConfigManager()
        self.device_manager = MIDIDeviceManager(self.config_manager)
        self.midi_handler = MIDIInputHandler()
        self.chord_detector = ChordDetector()
        self.chord_library = ChordLibrary()

        # Auto-open saved MIDI device
        selected_device = self.device_manager.get_selected_device()
        if selected_device:
            self.midi_handler.open_device(selected_device)

        # Create app context to share with main screen
        self.app_context = {
            "device_manager": self.device_manager,
            "midi_handler": self.midi_handler,
            "chord_detector": self.chord_detector,
            "chord_library": self.chord_library,
            "create_piano": self._create_piano_mode,
            "create_compendium": self._create_compendium_mode,
            "create_synth": self._create_synth_mode,
            "current_mode": "piano",
            "mode_before_config": "piano",
        }

    def on_mount(self):
        """Called when app mounts."""
        # Show config if no device, otherwise show main screen
        if not self.device_manager.get_selected_device():
            def on_config_closed(result):
                self.update_sub_title()
                # Show main screen after config
                main_screen = MainScreen(self.app_context)
                self.push_screen(main_screen)

            config = ConfigMode(self.device_manager)
            self.push_screen(config, on_config_closed)
        else:
            main_screen = MainScreen(self.app_context)
            self.push_screen(main_screen)

        self.update_sub_title()

    def update_sub_title(self):
        """Update sub title with device info."""
        selected = self.device_manager.get_selected_device()
        if selected:
            self.sub_title = f"🎹 Device: {selected}"
        else:
            self.sub_title = "⚠ No MIDI device selected (press C to configure)"

    def _create_piano_mode(self):
        """Create piano mode widget."""
        selected = self.device_manager.get_selected_device()
        if selected and not self.midi_handler.is_device_open():
            self.midi_handler.open_device(selected)

        return PianoMode(self.midi_handler, self.chord_detector)

    def _create_compendium_mode(self):
        """Create compendium mode widget."""
        return CompendiumMode(self.chord_library)

    def _create_synth_mode(self):
        """Create synth mode widget."""
        selected = self.device_manager.get_selected_device()
        if selected and not self.midi_handler.is_device_open():
            self.midi_handler.open_device(selected)

        return SynthMode(self.midi_handler)

    def on_unmount(self):
        """Clean up on exit."""
        self.midi_handler.close_device()


def main():
    """Main entry point."""
    app = AcordesApp()
    app.run()


if __name__ == "__main__":
    main()
