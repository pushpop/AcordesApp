"""ABOUTME: Drum sound parameter editor modal - allows real-time editing of ADSR, filter, oscillator.
ABOUTME: Per-pattern drum customization with live preview and undo support."""

from textual.screen import Screen
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Label
from textual.message import Message
from typing import Optional, Dict, Any, Callable, TYPE_CHECKING

from ..music.drum_presets import DRUM_PRESETS

if TYPE_CHECKING:
    from ..music.sequencer_engine import SequencerEngine


class DrumEditorScreen(Screen):
    """Modal screen for editing drum sound parameters."""

    CSS = """
    DrumEditorScreen {
        align: center middle;
        background: $surface 90%;
    }

    #editor-box {
        width: 90;
        height: auto;
        border: solid #FFA500;
        background: $panel;
    }

    #editor-header {
        width: 100%;
        text-align: center;
        color: $accent;
        background: $boost;
        padding: 1 2;
        border-bottom: solid #FFA500;
        text-style: bold;
    }

    #params-area {
        width: 100%;
        height: auto;
        padding: 1 1;
        layout: horizontal;
    }

    .param-column {
        width: 50%;
        height: auto;
        padding: 0 1;
    }

    #left-column {
        border-right: solid #FFA500 30%;
    }

    .section-title {
        color: #FFA500;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
    }

    .param-line {
        width: 100%;
        height: 1;
        margin-bottom: 1;
    }

    .param-name {
        width: 20;
        color: $text-muted;
    }

    .param-val {
        width: 15;
        color: $text;
        text-align: right;
    }

    .param-selected {
        background: #FFA500 40%;
    }

    #editor-footer {
        width: 100%;
        text-align: center;
        color: $text-muted;
        padding: 1 2;
        border-top: solid #FFA500;
        background: $boost;
    }
    """

    BINDINGS = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("left", "adjust_decrease", "Decrease", show=False),
        Binding("right", "adjust_increase", "Increase", show=False),
        Binding("shift+left", "adjust_decrease_fine", "Fine Decrease", show=False),
        Binding("shift+right", "adjust_increase_fine", "Fine Increase", show=False),
        Binding("space", "preview_drum", "Preview", show=False),
        Binding("r", "randomize_parameters", "Randomize", show=False),
        Binding("enter", "apply_changes", "Apply", show=False),
        Binding("escape", "cancel_changes", "Cancel", show=False),
    ]

    # Parameter definitions: (param_name, min_val, max_val, step, fine_step, unit, category)
    # Simplified for percussion-focused editing - only essential drum parameters
    PARAMETERS = [
        # ENVELOPE section - main shaper of drum character
        ("attack", 0.0, 0.01, 0.001, 0.0001, "s", "ENVELOPE"),
        ("decay", 0.05, 0.5, 0.01, 0.001, "s", "ENVELOPE"),
        ("release", 0.02, 0.3, 0.01, 0.001, "s", "ENVELOPE"),
        # FILTER section - tonal shaping
        ("cutoff_freq", 500, 16000, 500, 100, "Hz", "FILTER"),
        ("resonance", 0.0, 1.0, 0.05, 0.01, "", "FILTER"),
        # VOLUME section - output level
        ("volume", 0.0, 1.0, 0.1, 0.05, "", "VOLUME"),
    ]

    def __init__(
        self,
        drum_name: str,
        synth_params: Dict[str, Any],
        on_apply: Optional[Callable[[Dict[str, Any]], None]] = None,
        sequencer: Optional["SequencerEngine"] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_parameter_change: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """Initialize drum editor.

        Args:
            drum_name: Name of the drum being edited
            synth_params: Initial synth parameters dict
            on_apply: Optional callback when changes are applied
            sequencer: SequencerEngine for triggering preview sounds
            on_close: Optional callback called when editor closes (via Enter or Escape)
            on_parameter_change: Optional callback called whenever parameter changes (for real-time updates)
        """
        super().__init__()
        self.drum_name = drum_name
        self.synth_params = synth_params.copy()  # Work with a copy
        self.on_apply = on_apply
        self.on_close = on_close
        self.on_parameter_change = on_parameter_change
        self.sequencer = sequencer
        self.selected_idx = 0  # Keep for backward compatibility, but use two-column navigation
        self.preview_playing = False

        # Build column layout: left and right parameter lists
        self._build_column_layout()

    def _build_column_layout(self):
        """Organize parameters into left and right columns by section."""
        # Distribute sections to columns: Left (ENVELOPE, FILTER), Right (VOLUME)
        self.left_column = []
        self.right_column = []

        for param_data in self.PARAMETERS:
            section = param_data[6]
            if section in ("ENVELOPE", "FILTER"):
                self.left_column.append(param_data)
            else:  # VOLUME
                self.right_column.append(param_data)

    def compose(self):
        """Compose the editor layout with two-column parameter display."""
        with Vertical(id="editor-box"):
            yield Label(f"DRUM EDITOR: {self.drum_name.upper()}", id="editor-header")

            with Horizontal(id="params-area"):
                # Left column
                with Vertical(id="left-column", classes="param-column"):
                    current_section = None
                    for param_name, p_min, p_max, step, fine_step, unit, section in self.left_column:
                        if section != current_section:
                            yield Label(section, classes="section-title")
                            current_section = section

                        with Horizontal(classes="param-line"):
                            yield Label(param_name.replace("_", " ").title(), classes="param-name")
                            yield Label("0.00", classes="param-val")

                # Right column
                with Vertical(id="right-column", classes="param-column"):
                    current_section = None
                    for param_name, p_min, p_max, step, fine_step, unit, section in self.right_column:
                        if section != current_section:
                            yield Label(section, classes="section-title")
                            current_section = section

                        with Horizontal(classes="param-line"):
                            yield Label(param_name.replace("_", " ").title(), classes="param-name")
                            yield Label("0.00", classes="param-val")

            yield Label(
                "↑↓: Navigate | ←→: Adjust | Shift+←→: Fine | SPACE: Preview | R: Randomize | ENTER: Apply | ESC: Cancel",
                id="editor-footer"
            )

    def on_mount(self):
        """Setup after mounting."""
        self._update_display()

    def _update_display(self):
        """Update all parameter values in UI."""
        param_vals = self.query(".param-val")

        # Update all parameters - labels are in order (left column then right column)
        for idx, param_data in enumerate(self.PARAMETERS):
            param_name, p_min, p_max, step, fine_step, unit, _ = param_data
            value = self.synth_params.get(param_name, p_min)

            # Format value
            if isinstance(value, float):
                if unit == "s":
                    display = f"{value:.4f}s"
                elif unit == "Hz":
                    display = f"{int(value)}Hz"
                else:
                    display = f"{value:.2f}"
            else:
                display = str(value)

            # Update the corresponding label
            if idx < len(param_vals):
                label = param_vals[idx]
                # Highlight selected parameter
                if idx == self.selected_idx:
                    label.add_class("param-selected")
                else:
                    label.remove_class("param-selected")
                label.update(display)

    def action_move_up(self):
        """Move selection up."""
        if self.selected_idx > 0:
            self.selected_idx -= 1
            self._update_display()

    def action_move_down(self):
        """Move selection down."""
        if self.selected_idx < len(self.PARAMETERS) - 1:
            self.selected_idx += 1
            self._update_display()

    def action_adjust_increase(self):
        """Increase parameter value."""
        self._adjust_parameter(increase=True, fine=False)

    def action_adjust_decrease(self):
        """Decrease parameter value."""
        self._adjust_parameter(increase=False, fine=False)

    def action_adjust_increase_fine(self):
        """Increase parameter value (fine step)."""
        self._adjust_parameter(increase=True, fine=True)

    def action_adjust_decrease_fine(self):
        """Decrease parameter value (fine step)."""
        self._adjust_parameter(increase=False, fine=True)

    def _adjust_parameter(self, increase: bool, fine: bool):
        """Adjust selected parameter value."""
        param_data = self.PARAMETERS[self.selected_idx]
        param_name, p_min, p_max, step, fine_step, unit, _ = param_data

        current = self.synth_params.get(param_name, p_min)
        adjust_step = fine_step if fine else step

        # Adjust and clamp
        if increase:
            new_value = current + adjust_step
        else:
            new_value = current - adjust_step

        new_value = max(p_min, min(p_max, new_value))
        self.synth_params[param_name] = new_value
        self._update_display()

        # Note: Real-time synth updates are disabled during editing to prevent glitches
        # Parameters will be applied when user previews (SPACE) or confirms (ENTER)

    def action_preview_drum(self):
        """Preview drum with current parameter edits.

        Posts a preview request to TamborMode which will handle it via DrumVoiceManager.
        """
        # Post message for TamborMode to handle preview with current parameters
        self.post_message(self.PreviewRequested(self.drum_name, self.synth_params.copy()))

    def action_randomize_parameters(self):
        """Randomize all parameters except volume for creative exploration."""
        import random

        for param_name, p_min, p_max, step, fine_step, unit, _ in self.PARAMETERS:
            # Skip volume parameter
            if param_name == "volume":
                continue

            # Generate random value within parameter range
            if isinstance(p_min, float) or isinstance(p_max, float):
                # Float parameters: random value in range
                random_value = random.uniform(p_min, p_max)
            else:
                # Integer parameters: random value in range
                random_value = random.randint(int(p_min), int(p_max))

            self.synth_params[param_name] = random_value

        # Update display to show new values
        self._update_display()

        # Preview the randomized sound
        self.action_preview_drum()

    def action_apply_changes(self):
        """Apply changes and close editor."""
        if self.on_apply:
            self.on_apply(self.synth_params)
        if self.on_close:
            self.on_close()
        self.app.pop_screen()

    def action_cancel_changes(self):
        """Cancel and close without saving."""
        if self.on_close:
            self.on_close()
        self.app.pop_screen()

    class PreviewRequested(Message):
        """Message: User requested drum preview."""

        def __init__(self, drum_name: str, synth_params: Dict[str, Any]):
            super().__init__()
            self.drum_name = drum_name
            self.synth_params = synth_params
