#!/usr/bin/env python3
"""MIDI Piano TUI Application - Main Entry Point."""
import os
import sys

# Suppress the Pygame "hello" message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"

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
from music.synth_engine import SynthEngine

from modes.config_mode import ConfigMode
from modes.piano_mode import PianoMode
from modes.compendium_mode import CompendiumMode
from modes.synth_mode import SynthMode
from modes.metronome_mode import MetronomeMode
from modes.main_menu_mode import MainMenuMode
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
        align: center middle;
    }
    """

    BINDINGS = [
        Binding("0", "show_main_menu", "Menu", show=True),
        Binding("1", "show_piano", "Piano", show=True),
        Binding("2", "show_compendium", "Compendium", show=True),
        Binding("3", "show_synth", "Synth", show=True),
        Binding("4", "show_metronome", "Metronome", show=True),
        Binding("c", "show_config", "Config", show=True),
        Binding("backspace", "go_back", "Back", show=True),
        Binding("escape", "quit_app", "Quit", show=True),
    ]

    def __init__(self, app_context):
        super().__init__()
        self.app_context = app_context
        self.mode_history = []

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
        self.action_show_main_menu(save_history=False)

    def _record_history(self):
        """Record current mode to history if it's different from the last entry."""
        current = self.app_context.get("current_mode")
        if current:
            if not self.mode_history or self.mode_history[-1] != current:
                self.mode_history.append(current)

    def action_go_back(self):
        """Go back to the previous mode."""
        if not self.mode_history:
            # If no history, just show main menu
            if self.app_context.get("current_mode") != "main_menu":
                self.action_show_main_menu(save_history=False)
            return

        previous_mode = self.mode_history.pop()
        
        # Dispatch to the appropriate show method without saving history again
        if previous_mode == "main_menu":
            self.action_show_main_menu(save_history=False)
        elif previous_mode == "piano":
            self.action_show_piano(save_history=False)
        elif previous_mode == "compendium":
            self.action_show_compendium(save_history=False)
        elif previous_mode == "synth":
            self.action_show_synth(save_history=False)
        elif previous_mode == "metronome":
            self.action_show_metronome(save_history=False)

    def action_show_main_menu(self, save_history=True):
        """Show main menu mode."""
        if save_history:
            self._record_history()

        content = self.query_one("#content-area")
        content.remove_children()

        main_menu = self.app_context["create_main_menu"](self)
        content.mount(main_menu)
        self.app_context["current_mode"] = "main_menu"


    def action_show_piano(self, save_history=True):
        """Show piano mode."""
        if save_history:
            self._record_history()

        content = self.query_one("#content-area")
        content.remove_children()

        piano = self.app_context["create_piano"]()
        content.mount(piano)
        self.app_context["current_mode"] = "piano"

    def action_show_compendium(self, save_history=True):
        """Show compendium mode."""
        if save_history:
            self._record_history()

        content = self.query_one("#content-area")
        content.remove_children()

        compendium = self.app_context["create_compendium"]()
        content.mount(compendium)
        self.app_context["current_mode"] = "compendium"

    def action_show_synth(self, save_history=True):
        """Show synth mode."""
        if save_history:
            self._record_history()

        content = self.query_one("#content-area")
        content.remove_children()

        synth = self.app_context["create_synth"]()
        content.mount(synth)
        self.app_context["current_mode"] = "synth"
        
    def action_show_metronome(self, save_history=True):
        """Show metronome mode."""
        if save_history:
            self._record_history()

        content = self.query_one("#content-area")
        content.remove_children()

        metronome = self.app_context["create_metronome"]()
        content.mount(metronome)
        self.app_context["current_mode"] = "metronome"

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
            previous_mode = self.app_context.get("mode_before_config", "main_menu")
            if previous_mode == "piano":
                self.action_show_piano(save_history=False)
            elif previous_mode == "compendium":
                self.action_show_compendium(save_history=False)
            elif previous_mode == "synth":
                self.action_show_synth(save_history=False)
            elif previous_mode == "metronome":
                self.action_show_metronome(save_history=False)
            else: # Defaults to main_menu
                self.action_show_main_menu(save_history=False)

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

    VERSION = "1.4.0"
    CSS = """
    """

    def __init__(self):
        super().__init__()
        self.title = f"Acordes v{self.VERSION}"
        # Initialize config and components
        self.config_manager = ConfigManager()
        self.device_manager = MIDIDeviceManager(self.config_manager)
        self.midi_handler = MIDIInputHandler()
        self.chord_detector = ChordDetector()
        self.chord_library = ChordLibrary()
        self.synth_engine = SynthEngine()

        # Pre-load/Warm-up audio system
        self.synth_engine.warm_up()

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
            "synth_engine": self.synth_engine,
            "config_manager": self.config_manager,
            "create_main_menu": self._create_main_menu_mode,
            "create_piano": self._create_piano_mode,
            "create_compendium": self._create_compendium_mode,
            "create_synth": self._create_synth_mode,
            "create_metronome": self._create_metronome_mode,
            "current_mode": "main_menu",
            "mode_before_config": "main_menu",
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

    def _create_main_menu_mode(self, main_screen):
        """Create main menu widget."""
        return MainMenuMode(main_screen)

    def _create_piano_mode(self):
        """Create piano mode widget."""
        selected = self.device_manager.get_selected_device()
        if selected and not self.midi_handler.is_device_open():
            self.midi_handler.open_device(selected)

        return PianoMode(self.midi_handler, self.chord_detector, self.synth_engine)

    def _create_compendium_mode(self):
        """Create compendium mode widget."""
        return CompendiumMode(self.chord_library, self.synth_engine)

    def _create_synth_mode(self):
        """Create synth mode widget."""
        selected = self.device_manager.get_selected_device()
        if selected and not self.midi_handler.is_device_open():
            self.midi_handler.open_device(selected)

        return SynthMode(self.midi_handler, self.synth_engine, self.config_manager)

    def _create_metronome_mode(self):
        """Create metronome mode widget."""
        return MetronomeMode()

    def on_unmount(self):
        """Clean up on exit."""
        self.midi_handler.close_device()
        # Clear the terminal screen
        os.system('cls' if os.name == 'nt' else 'clear')


def main():
    """Main entry point."""
    app = AcordesApp()
    app.run()


if __name__ == "__main__":
    main()
