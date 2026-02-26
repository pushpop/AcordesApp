"""Main Menu Mode for Acordes."""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Center
from textual.widgets import Button, Static, Label
from textual.widget import Widget
from textual import events
from components.header_widget import HeaderWidget

class MainMenuMode(Vertical):
    """A widget to display the main menu."""

    DEFAULT_CSS = """
    MainMenuMode {
        align: center middle;
        width: 100%;
        height: 100%;
        border: heavy $accent;
        padding: 1;
    }

    #main-menu-buttons {
        width: auto;
        height: auto;
        align: center middle;
    }

    #main-menu-buttons Button {
        width: 16;
        height: 12;
        margin: 0 1;
        border: tall $primary;
    }

    /* Visual feedback for focused button */
    #main-menu-buttons Button:focus {
        background: $accent;
        color: $text;
        text-style: bold;
        border: tall $primary-lighten-3;
    }
    """

    def __init__(self, main_screen, **kwargs):
        super().__init__(**kwargs)
        self.main_screen = main_screen

    def compose(self) -> ComposeResult:
        """Create the main menu layout."""
        yield HeaderWidget(title="M A I N   M E N U", subtitle="Select a mode to begin")

        with Center():
            with Horizontal(id="main-menu-buttons"):
                yield Button("Piano", id="piano_button", variant="primary")
                yield Button("Compendium", id="compendium_button", variant="primary")
                yield Button("Synth", id="synth_button", variant="primary")
                yield Button("Metronome", id="metronome_button", variant="primary")
                yield Button("Tambor", id="tambor_button", variant="primary")

    def on_mount(self) -> None:
        """Focus the first button when the menu is mounted."""
        self.query_one("#piano_button").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "piano_button":
            self.main_screen.action_show_piano()
        elif event.button.id == "compendium_button":
            self.main_screen.action_show_compendium()
        elif event.button.id == "synth_button":
            self.main_screen.action_show_synth()
        elif event.button.id == "metronome_button":
            self.main_screen.action_show_metronome()
        elif event.button.id == "tambor_button":
            self.main_screen.action_show_tambor()

    def on_key(self, event: events.Key) -> None:
        """Handle directional keys for focus navigation."""
        if event.key == "left":
            self.app.action_focus_previous()
        elif event.key == "right":
            self.app.action_focus_next()
        elif event.key == "up":
            self.app.action_focus_previous()
        elif event.key == "down":
            self.app.action_focus_next()
