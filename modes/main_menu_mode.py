# ABOUTME: Main menu mode - displays the five mode selection buttons.
# ABOUTME: Input coalescing prevents CPU spikes from rapid key repeat on ARM.

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Center
from textual.widgets import Button, Static, Label
from textual.widget import Widget
from textual import events
from components.header_widget import HeaderWidget
from gamepad.actions import GP

# Ordered list of button IDs matching left-to-right layout.
_BUTTON_IDS = [
    "piano_button",
    "compendium_button",
    "synth_button",
    "metronome_button",
    "tambor_button",
]

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
        width: 100%;
        height: auto;
        align: center middle;
    }

    #main-menu-buttons Button {
        width: 1fr;
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
        # Accumulated navigation delta from rapid keypresses.
        # Coalesced into a single .focus() call per frame to avoid
        # queuing multiple CSS-state changes and renders on ARM.
        self._nav_delta: int = 0
        self._nav_timer = None

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
        self._register_gamepad_callbacks()

    def on_mode_resume(self) -> None:
        """Called by MainScreen when showing this cached mode again.

        MainScreen defers this call via call_later so the display toggle has
        already been processed; focus() fires on the same tick as resume.
        """
        self.query_one("#piano_button").focus()
        self._register_gamepad_callbacks()

    def on_mode_pause(self) -> None:
        """Called by MainScreen when hiding this mode."""
        gp = self.main_screen.app_context.get("gamepad_handler")
        if gp is not None:
            gp.clear_callbacks()

    def _register_gamepad_callbacks(self) -> None:
        """Register per-mode gamepad callbacks for main menu navigation."""
        gp = self.main_screen.app_context.get("gamepad_handler")
        if gp is None:
            return
        gp.clear_callbacks()
        gp.set_button_callback(GP.DPAD_LEFT,  lambda: self._gp_nav(-1))
        gp.set_button_callback(GP.DPAD_RIGHT, lambda: self._gp_nav(1))
        gp.set_button_callback(GP.CONFIRM,    self._gp_confirm)
        gp.set_button_callback(GP.BACK,       self.main_screen.action_quit_app)

    def _gp_nav(self, delta: int) -> None:
        """Move menu selection left (delta=-1) or right (delta=1)."""
        buttons = [self.query_one(f"#{bid}") for bid in _BUTTON_IDS]
        focused = self.app.focused
        try:
            idx = buttons.index(focused)
        except ValueError:
            idx = 0
        new_idx = max(0, min(len(buttons) - 1, idx + delta))
        buttons[new_idx].focus()

    def _gp_confirm(self) -> None:
        """Activate the currently focused menu button."""
        focused = self.app.focused
        if focused is not None and hasattr(focused, "press"):
            focused.press()

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
        """Handle directional keys with input coalescing.

        Rapid keypresses accumulate into _nav_delta. A short timer fires once
        per burst and applies all movement as a single .focus() call, producing
        one CSS state change and one render regardless of how many keys arrived.
        """
        if event.key in ("left", "up"):
            self._nav_delta -= 1
        elif event.key in ("right", "down"):
            self._nav_delta += 1
        else:
            return

        # Cancel any pending navigation and reschedule.
        # One frame at 30fps is ~33ms; 40ms gives a small margin.
        if self._nav_timer is not None:
            self._nav_timer.stop()
        self._nav_timer = self.set_timer(0.040, self._apply_nav)

    def _apply_nav(self) -> None:
        """Apply accumulated navigation delta as a single focus change."""
        self._nav_timer = None
        delta = self._nav_delta
        self._nav_delta = 0
        if delta == 0:
            return

        buttons = [self.query_one(f"#{bid}") for bid in _BUTTON_IDS]
        focused = self.app.focused
        try:
            idx = buttons.index(focused)
        except ValueError:
            idx = 0

        new_idx = max(0, min(len(buttons) - 1, idx + delta))
        buttons[new_idx].focus()
