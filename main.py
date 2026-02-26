#!/usr/bin/env python3
"""MIDI Piano TUI Application - Main Entry Point."""
import os
import sys

# Suppress the Pygame "hello" message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"

# Note: On Windows, mido will auto-detect available MIDI backends
# We don't force a specific backend to avoid DLL issues

from typing import Optional

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
from modes.tambor.tambor_mode import TamborMode
from components.confirmation_dialog import ConfirmationDialog


class SynthHelpBar(Static):
    """ABOUTME: Help bar displaying Synth keybinds - shown only in Synth mode.
    ABOUTME: Displays keyboard shortcuts for Synth operations on two lines."""

    def render(self) -> str:
        """Render the help bar with two lines of keybinds."""
        line1 = "WASD: Navigate | Q/E: Adjust | _: Randomize | ENTER: Focus | ,/.: Presets"
        line2 = r"\[/\]: Volume | Ctrl+N: Save | Ctrl+S: Update | SPACE: Panic | -: Random All"
        return f"{line1}\n{line2}"


class TamborHelpBar(Static):
    """ABOUTME: Help bar displaying Tambor keybinds - shown only in Tambor mode.
    ABOUTME: Displays keyboard shortcuts for all Tambor operations on two lines."""

    def render(self) -> str:
        """Render the help bar with two lines of keybinds."""
        line1 = "↑↓: Drums | ←→: Steps/M-S | SPACE: Play/Stop | ENTER: Toggle | E: Edit | M: Mute | S: Solo | H: Humanize"
        line2 = "R: Random | F: Fill | C: Clear | T: PRE-SCALE | N: Pattern | +/-: Steps"
        return f"{line1}\n{line2}"


class MetronomeHelpBar(Static):
    """ABOUTME: Help bar displaying Metronome keybinds - shown only in Metronome mode.
    ABOUTME: Displays keyboard shortcuts for metronome control on two lines."""

    def render(self) -> str:
        """Render the help bar with two lines of keybinds."""
        line1 = "P / SPACE: Start/Stop | ↑: Tempo + | ↓: Tempo - | ←: Time Sig - | →: Time Sig +"
        line2 = ""
        return line1 if not line2 else f"{line1}\n{line2}"


class CompendiumHelpBar(Static):
    """ABOUTME: Help bar displaying Compendium keybinds - shown only in Compendium mode.
    ABOUTME: Displays keyboard shortcuts for chord library browsing."""

    def render(self) -> str:
        """Render the help bar with two lines of keybinds."""
        line1 = "SPACE: Play Chord | E: Expand All | ↑↓←→: Navigate"
        line2 = ""
        return line1 if not line2 else f"{line1}\n{line2}"


class MainScreen(Screen):
    """Main screen with split layout."""

    CSS = """
    MainScreen {
        layout: vertical;
    }

    #content-area {
        height: 1fr;
        width: 100%;
        align: center middle;
    }

    #content-area > .mode-mounting {
        display: none;
    }

    #synth-help-bar {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        padding: 0;
        margin: 0;
        border-top: solid $accent;
    }

    #tambor-help-bar {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        padding: 0;
        margin: 0;
        border-top: solid $accent;
    }

    #metronome-help-bar {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        padding: 0;
        margin: 0;
        border-top: solid $accent;
    }

    #compendium-help-bar {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        padding: 0;
        margin: 0;
        border-top: solid $accent;
    }
    """

    BINDINGS = [
        Binding("0", "show_main_menu", "Menu", show=True),
        Binding("1", "show_piano", "Piano", show=True),
        Binding("2", "show_compendium", "Compendium", show=True),
        Binding("3", "show_synth", "Synth", show=True),
        Binding("4", "show_metronome", "Metronome", show=True),
        Binding("5", "show_tambor", "Tambor", show=True),
        Binding("c", "show_config", "Config", show=True),
        Binding("backspace", "go_back", "Back", show=True),
        Binding("escape", "quit_app", "Quit", show=True),
    ]

    def __init__(self, app_context):
        super().__init__()
        self.app_context = app_context
        self.mode_history = []
        self._help_bars: dict[str, Optional[Static]] = {
            "synth": None,
            "tambor": None,
            "metronome": None,
            "compendium": None,
        }

    def compose(self):
        """Compose the main screen layout."""
        yield Header()

        # Content area for Piano or Compendium - NO CONTAINER
        with Container(id="content-area"):
            pass

        # Help bar will be mounted dynamically when in Tambor mode
        # It's not yielded here because we only want it visible in Tambor mode

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
        elif previous_mode == "tambor":
            self.action_show_tambor(save_history=False)

    def action_show_main_menu(self, save_history=True):
        """Show main menu mode."""
        if save_history:
            self._record_history()

        content = self.query_one("#content-area")
        content.remove_children()

        main_menu = self.app_context["create_main_menu"](self)
        content.mount(main_menu)
        self.app_context["current_mode"] = "main_menu"


    def _switch_mode(self, create_fn, mode_name: str):
        """Central mode-switch helper.

        Always silences the synth before swapping widgets so that any notes
        held in the outgoing mode (Piano, Compendium, Synth) cannot latch into
        the incoming mode.  The incoming mode's on_mount will re-register its
        own MIDI callbacks, so there is no risk of the old callback firing after
        the switch.
        """
        # Silence any notes that may still be held from the current mode.
        self.app_context["synth_engine"].all_notes_off()

        content = self.query_one("#content-area")
        content.remove_children()
        mode_widget = create_fn()
        # Hide mode during mounting to prevent cascading widget render artifacts
        mode_widget.add_class("mode-mounting")
        content.mount(mode_widget)

        # Reveal the mode after it's fully composed
        def show_mode():
            mode_widget.remove_class("mode-mounting")

        self.call_later(show_mode)

        # Give focus to the mounted mode if it supports focus (for BINDINGS to work)
        if hasattr(mode_widget, 'can_focus') and mode_widget.can_focus:
            mode_widget.focus()

        # Manage mode-specific help bars: mount only for modes that have them
        modes_with_help = {
            "synth": SynthHelpBar,
            "tambor": TamborHelpBar,
            "metronome": MetronomeHelpBar,
            "compendium": CompendiumHelpBar,
        }

        if mode_name in modes_with_help:
            # Mount the appropriate help bar if not already mounted
            if self._help_bars[mode_name] is None:
                help_bar_class = modes_with_help[mode_name]
                self._help_bars[mode_name] = help_bar_class(id=f"{mode_name}-help-bar")
                self.mount(self._help_bars[mode_name])

        # Unmount help bars for modes we're not in
        for mode, help_bar in self._help_bars.items():
            if mode != mode_name and help_bar is not None:
                help_bar.remove()
                self._help_bars[mode] = None

        self.app_context["current_mode"] = mode_name

    def action_show_piano(self, save_history=True):
        """Show piano mode."""
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_piano"], "piano")

    def action_show_compendium(self, save_history=True):
        """Show compendium mode."""
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_compendium"], "compendium")

    def action_show_synth(self, save_history=True):
        """Show synth mode."""
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_synth"], "synth")

    def action_show_metronome(self, save_history=True):
        """Show metronome mode."""
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_metronome"], "metronome")

    def action_show_tambor(self, save_history=True):
        """Show Tambor drum machine mode."""
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_tambor"], "tambor")

    def action_show_config(self):
        """Show config modal."""
        # Remember current mode
        self.app_context["mode_before_config"] = self.app_context["current_mode"]

        def on_closed(result):
            # Update footer
            self.app.update_sub_title()

            # Silence any notes that may have been left held before config opened
            self.app_context["synth_engine"].all_notes_off()

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
            elif previous_mode == "tambor":
                self.action_show_tambor(save_history=False)
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

    VERSION = "1.5.0"
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
            "create_tambor": self._create_tambor_mode,
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
        return MetronomeMode(self.config_manager)

    def _create_tambor_mode(self):
        """Create Tambor drum machine mode widget."""
        return TamborMode(
            config_manager=self.config_manager,
            synth_engine=self.synth_engine,
            midi_handler=self.midi_handler
        )

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
