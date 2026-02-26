"""ABOUTME: Tambor drum machine mode - displays 16-step sequencer grid and drum controls.
ABOUTME: Handles layout, key bindings, pattern editing, and file persistence (Phase 2+)."""

from textual.widget import Widget
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import Static, Label
from textual.binding import Binding
from typing import Set, Tuple, List, Optional, Dict, Any
import time
import threading
from .components.header_widget import HeaderWidget
from .components.pattern_selector import PatternSelector, PatternSelectorScreen
from .components.drum_editor import DrumEditorScreen
from .components.fill_selector import FillSelectorScreen
from .music.pre_scale import PreScale, PRE_SCALE_VALUES, get_pre_scale_name
from .music.sequencer_engine import SequencerEngine
from .music.drum_presets import DRUM_PRESETS
from .music.fill_presets import FILL_TEMPLATES, expand_fill_to_steps
from .music.drum_voice_manager import DrumVoiceManager
from .music.pattern_manager import PatternManager
from .music.audio_thread import PatternSaver
from .music.humanize import Humanizer


class SimpleConfigManager:
    """Simple config manager stub for standalone use."""

    def __init__(self, bpm: int = 120):
        self.bpm = bpm

    def get_bpm(self) -> int:
        return self.bpm

    def set_bpm(self, bpm: int):
        self.bpm = max(40, min(240, bpm))  # Clamp reasonable range


class GridCell(Static):
    """A single cell in the 16-step sequencer grid."""

    DEFAULT_CSS = """
    GridCell {
        width: 3;
        height: 2;
        margin: 0;
        padding: 0;
        content-align: center middle;
        background: #121212;
        color: $text-muted;
    }

    /* Light orange border for cells in steps 0-3 and 8-11 */
    GridCell.measure-light {
        border: solid #FFA500 40%;
    }

    /* Dark orange border for cells in steps 4-7 and 12-15 */
    GridCell.measure-dark {
        border: solid #FF5900 40%;
    }

    GridCell.active {
        border: inner #FF5900;
    }

    GridCell.focused {
        border: inner #FFFF00;
        text-style: bold;
    }

    GridCell.active.focused {
        background: #121212;
        border: inner #FFFF00 90%;
    }

    GridCell.playing {
        background: #FFFF00 20%;
        border: solid #FFFF00;
    }

    GridCell.active.playing {
        background: $accent;
        border: heavy #FFFF00;
    }
    """

    def __init__(self, step: int, drum: int):
        super().__init__("")
        self.step = step
        self.drum = drum
        self.is_active = False
        self._set_measure_class()

    def _set_measure_class(self):
        """Set the measure color class based on step position and drum row."""
        measure_group = (self.step // 4) % 2
        row_parity = self.drum % 2
        is_dark = (measure_group + row_parity) % 2 == 1

        if is_dark:
            self.add_class("measure-dark")
        else:
            self.add_class("measure-light")

    def on_mount(self):
        """Set initial display state after mounting."""
        self.update_display()

    def update_display(self):
        """Update the visual state of the cell."""
        if self.is_active:
            self.add_class("active")
        else:
            self.remove_class("active")
        self.update("")

    def toggle(self):
        """Toggle the active state."""
        self.is_active = not self.is_active
        self.update_display()


class DrumRow(Static):
    """A row in the sequencer representing one drum sound."""

    DEFAULT_CSS = """
    DrumRow {
        layout: horizontal;
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
        border-left: round $accent;
        border-right: round $accent;
    }

    DrumRow #drum-label {
        width: 20;
        height: auto;
        content-align: center middle;
        text-align: right;
        padding: 0 1;
        margin: 0;
        color: $accent;
        text-style: bold;
    }

    DrumRow.selected #drum-label {
        color: #ffff00;
        background: #666666;
        text-style: bold;
    }

    DrumRow #mute-solo-state {
        width: auto;
        height: auto;
        layout: horizontal;
        padding: 0 1;
        margin: 0;
        content-align: center middle;
    }

    DrumRow #mute-button {
        width: 3;
        height: 1;
        border: solid $accent 40%;
        padding: 0;
        margin: 0;
        content-align: center middle;
        color: #cccccc;
        background: #222222;
        text-style: bold;
    }

    DrumRow #mute-button.muted {
        background: #8B0000;
        border: inner #ff0000 80%;
        text-style: bold;
    }

    DrumRow #mute-button.focused {
        border: heavy $accent;
        background: $panel;
        color: #8B0000;
        text-style: bold;
    }

    DrumRow #mute-button.muted.focused {
        border: inner #8B0000;
        background: #8B0000 80%;
        text-style: bold;
    }

    DrumRow #solo-button {
        width: 3;
        height: 1;
        border: solid $accent 40%;
        padding: 0;
        margin: 0 1;
        content-align: center middle;
        color: #cccccc;
        background: #222222;
        text-style: bold;
    }

    DrumRow #solo-button.soloed {
        background: #DAA520;
        border: inner #ffff00 80%;
        text-style: bold;
    }

    DrumRow #solo-button.focused {
        border: heavy $accent;
        background: $panel;
        color: #ffff00;
        text-style: bold;
    }

    DrumRow #solo-button.soloed.focused {
        border: inner #ffff00;
        background: #DAA520;
        color: #ffff00;
        text-style: bold;
    }

    DrumRow #drum-steps {
        width: 1fr;
        height: auto;
        layout: horizontal;
        border: none;
        padding: 0;
        margin: 0;
    }
    """

    def __init__(self, drum_name: str, drum_index: int, num_steps: int = 16, pattern_data: list = None):
        super().__init__()
        self.drum_name = drum_name
        self.drum_index = drum_index
        self.num_steps = max(2, min(32, num_steps))  # Clamp to valid range
        self.cells = []
        self.pattern_data = pattern_data  # Pattern data to initialize cells with
        self.is_muted = False
        self.is_soloed = False
        self.mute_button_focused = False  # Track if mute button has focus
        self.solo_button_focused = False  # Track if solo button has focus

    def compose(self):
        """Compose the drum row."""
        yield Label(self.drum_name, id="drum-label")

        with Horizontal(id="mute-solo-state"):
            # Mute button indicator - always shows [M] with color indicating state
            mute_label = Label("[M]", id="mute-button")
            if self.is_muted:
                mute_label.add_class("muted")
            yield mute_label

            # Solo button indicator - always shows [S] with color indicating state
            solo_label = Label("[S]", id="solo-button")
            if self.is_soloed:
                solo_label.add_class("soloed")
            yield solo_label

        with Horizontal(id="drum-steps"):
            for step in range(self.num_steps):
                cell = GridCell(step, self.drum_index)
                self.cells.append(cell)

                # Set cell active state from pattern_data if available
                if self.pattern_data and step < len(self.pattern_data):
                    step_data = self.pattern_data[step]
                    if isinstance(step_data, dict):
                        cell.is_active = step_data.get("active", False)
                    else:
                        cell.is_active = bool(step_data)
                    cell.update_display()

                yield cell

    def get_pattern(self) -> list:
        """Return the pattern for this drum as a list of step dicts."""
        # This method is used for saving patterns
        # We need to get the full step data, not just is_active
        # This will be overridden by getting pattern from TamborMode.patterns directly
        return [cell.is_active for cell in self.cells]

    def set_pattern(self, pattern: list):
        """Set the pattern for this drum from a list of step dicts."""
        for step, cell in enumerate(self.cells):
            if step < len(pattern):
                # Handle both dict and bool formats for backward compatibility
                if isinstance(pattern[step], dict):
                    cell.is_active = pattern[step].get("active", False)
                else:
                    cell.is_active = bool(pattern[step])
            else:
                cell.is_active = False
            cell.update_display()

    def toggle_step(self, step: int):
        """Toggle a specific step."""
        if 0 <= step < len(self.cells):
            self.cells[step].toggle()

    def update_mute_solo_display(self, is_muted: bool, is_soloed: bool):
        """Update the mute/solo display indicators."""
        self.is_muted = is_muted
        self.is_soloed = is_soloed

        # Update mute button display
        try:
            mute_button = self.query_one("#mute-button", Label)
            # Always display [M], only change styling
            if is_muted:
                mute_button.add_class("muted")
            else:
                mute_button.remove_class("muted")

            # Update focus state
            if self.mute_button_focused:
                mute_button.add_class("focused")
            else:
                mute_button.remove_class("focused")
        except:
            pass

        # Update solo button display
        try:
            solo_button = self.query_one("#solo-button", Label)
            # Always display [S], only change styling
            if is_soloed:
                solo_button.add_class("soloed")
            else:
                solo_button.remove_class("soloed")

            # Update focus state
            if self.solo_button_focused:
                solo_button.add_class("focused")
            else:
                solo_button.remove_class("focused")
        except:
            pass

    def set_mute_button_focus(self, focused: bool):
        """Set focus state for mute button."""
        self.mute_button_focused = focused
        self.solo_button_focused = False  # Clear solo focus
        self.update_mute_solo_display(self.is_muted, self.is_soloed)

    def set_solo_button_focus(self, focused: bool):
        """Set focus state for solo button."""
        self.solo_button_focused = focused
        self.mute_button_focused = False  # Clear mute focus
        self.update_mute_solo_display(self.is_muted, self.is_soloed)

    def clear_button_focus(self):
        """Clear all button focus."""
        self.mute_button_focused = False
        self.solo_button_focused = False
        self.update_mute_solo_display(self.is_muted, self.is_soloed)


class ControlPanel(Static):
    """Control panel showing BPM, pattern #, and playback state."""

    DEFAULT_CSS = """
    ControlPanel {
        layout: horizontal;
        width: 100%;
        height: auto;
        background: $boost;
        color: $text;
        padding: 1 2;
        border: round $accent;
    }

    ControlPanel Label {
        width: auto;
        height: auto;
        margin-right: 4;
    }
    """

    def __init__(self):
        super().__init__()
        self.bpm = 120
        self.pattern = 1
        self.total_patterns = 64
        self.playback_state = "STOPPED"
        self.current_step = 0
        self.max_steps = 16
        self.pre_scale = "4 steps/beat"
        self.pattern_is_dirty = False  # Track unsaved changes
        self.focus_drum_name = "Kick"  # Current focused drum
        self.focus_info = "Step 01"  # Current focus info (step number or button type)
        self.humanize_info = "Humanize: OFF"  # Current humanize status
        self.fill_info = "Fill: None"  # Current fill assignment

    def compose(self):
        """Compose the control panel."""
        yield Label(f"BPM: {self.bpm}", id="bpm-label")
        yield Label(f"Pattern: {self.pattern:02d}/{self.total_patterns}", id="pattern-label")
        yield Label(f"State: {self.playback_state}", id="state-label")
        yield Label(f"Step: {self.current_step + 1:02d}/{self.max_steps}", id="step-label")
        yield Label(f"PRE-SCALE: {self.pre_scale}", id="pre-scale-label")
        yield Label(f"{self.humanize_info}", id="humanize-label")
        yield Label(f"{self.fill_info}", id="fill-label")
        yield Label(f"Focus: {self.focus_drum_name} {self.focus_info}", id="focus-label")

    def update_bpm(self, bpm: int):
        """Update BPM display."""
        self.bpm = bpm
        try:
            self.query_one("#bpm-label").update(f"BPM: {self.bpm}")
        except:
            pass

    def update_pattern(self, pattern: int, is_dirty: bool = False):
        """Update pattern number display with optional unsaved indicator."""
        self.pattern = pattern
        self.pattern_is_dirty = is_dirty
        self._update_pattern_display()

    def _update_pattern_display(self):
        """Update the pattern label with dirty indicator if needed."""
        dirty_marker = " *" if self.pattern_is_dirty else ""
        try:
            self.query_one("#pattern-label").update(f"Pattern: {self.pattern:02d}/{self.total_patterns}{dirty_marker}")
        except:
            pass

    def update_state(self, state: str):
        """Update playback state display."""
        self.playback_state = state
        try:
            self.query_one("#state-label").update(f"State: {self.playback_state}")
        except:
            pass

    def update_step(self, step: int):
        """Update current step display."""
        self.current_step = step
        try:
            self.query_one("#step-label").update(f"Step: {self.current_step + 1:02d}/{self.max_steps}")
        except:
            pass

    def update_step_count(self, max_steps: int):
        """Update the maximum step count display."""
        self.max_steps = max_steps
        try:
            self.query_one("#step-label").update(f"Step: {self.current_step + 1:02d}/{self.max_steps}")
        except:
            pass

    def update_pre_scale_info(self, info: str):
        """Update PRE-SCALE display."""
        self.pre_scale = info
        try:
            self.query_one("#pre-scale-label").update(f"PRE-SCALE: {self.pre_scale}")
        except:
            pass

    def update_humanize_info(self, info: str):
        """Update humanize status display."""
        self.humanize_info = info
        try:
            self.query_one("#humanize-label").update(self.humanize_info)
        except:
            pass

    def update_fill_info(self, info: str):
        """Update fill pattern status display."""
        self.fill_info = info
        try:
            self.query_one("#fill-label").update(self.fill_info)
        except:
            pass

    def update_focus_info(self, drum_name: str, focus_info: str):
        """Update focus information display."""
        self.focus_drum_name = drum_name
        self.focus_info = focus_info
        try:
            self.query_one("#focus-label").update(f"Focus: {self.focus_drum_name} {self.focus_info}")
        except:
            pass

    def update_info(self, info: str):
        """Update transient feedback info (e.g., randomize strategy applied)."""
        try:
            self.query_one("#focus-label").update(info)
        except:
            pass


class TamborMode(Vertical):
    """Main drum machine mode - 16-step sequencer with 8 drum sounds."""

    can_focus = True

    BINDINGS = [
        Binding("up", "move_drum_up", "Up", show=False),
        Binding("down", "move_drum_down", "Down", show=False),
        Binding("left", "move_step_left", "Left", show=False),
        Binding("right", "move_step_right", "Right", show=False),
        Binding("enter", "toggle_step", "Toggle Step", show=False),
        Binding("space", "toggle_playback", "Play/Stop", show=False),
        Binding("p", "toggle_playback", "Play/Stop", show=False),
        Binding("t", "cycle_pre_scale", "PRE-SCALE", show=False),
        Binding("n", "open_pattern_selector", "Pattern", show=False),
        Binding("e", "edit_drum", "Edit", show=False),
        Binding("c", "clear_pattern", "Clear", show=False),
        Binding("ctrl+z", "undo_delete", "Undo", show=False),
        Binding("plus,shift+equal", "increase_step_count", "More Steps", show=False),
        Binding("minus", "decrease_step_count", "Fewer Steps", show=False),
        Binding("m", "toggle_mute", "Mute", show=False),
        Binding("s", "toggle_solo", "Solo", show=False),
        Binding("h", "toggle_humanize", "Humanize", show=False),
        Binding("r", "randomize_drum", "Randomize", show=False),
        Binding("f", "open_fill_selector", "Fill", show=False),
    ]

    CSS = """
    TamborMode {
        width: 100%;
        height: auto;
        background: $surface;
        layout: vertical;
    }

    TamborMode > ControlPanel {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }

    TamborMode > DrumRow {
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }
    """

    DRUM_SOUNDS = [
        "Kick",
        "Snare",
        "Closed HH",
        "Open HH",
        "Clap",
        "Tom Hi",
        "Tom Mid",
        "Tom Low",
    ]

    def __init__(self, config_manager: Optional[Any] = None, synth_engine: Optional[Any] = None, midi_handler: Optional[Any] = None):
        """
        Initialize TamborMode with Acordes integration.

        Args:
            config_manager: Acordes ConfigManager for shared BPM (required)
            synth_engine: Acordes SynthEngine for audio synthesis (required)
            midi_handler: Optional Acordes MIDIInputHandler for future MIDI integration
        """
        super().__init__()
        self.drum_rows: list[DrumRow] = []
        self.control_panel: ControlPanel = None
        self.cursor_drum = 0
        self.cursor_step = 0
        self.cursor_focus = "grid"  # "grid", "mute", or "solo" - which area has focus

        # 64-pattern support with lazy loading
        self.patterns: Dict[int, Optional[List]] = {i: None for i in range(1, 65)}
        self.pattern_step_counts: Dict[int, int] = {i: 16 for i in range(1, 65)}
        self.pattern_bpms: Dict[int, int] = {i: 120 for i in range(1, 65)}
        self.pattern_dirty: set[int] = set()  # Track which patterns need saving
        self.current_pattern = 1
        self.current_step_count = 16  # Will be updated when pattern loads

        # Pattern file manager - store in presets/tambor/ for Acordes integration
        # This keeps Tambor patterns separate from synth presets
        self.pattern_manager = PatternManager("presets/tambor")

        # Background pattern saver for non-blocking saves
        self._pattern_saver = PatternSaver(self.pattern_manager)

        # Undo system for cleared patterns
        self.undo_stack: List[Tuple[int, List]] = []  # Stack of (pattern_num, pattern_data)

        # Initialize pattern 1 with empty pattern so grid is visible on startup
        # Will be replaced with loaded pattern in on_mount() if available
        self._init_pattern(1)

        self.playback_state = "STOPPED"
        self.current_pre_scale = PreScale.SCALE_4  # Default: 4 steps per beat
        self.pre_scale_values = PRE_SCALE_VALUES
        self.pre_scale_index = 2  # Index of SCALE_4 in the list

        # Mute/solo toggle state (drum_idx in these sets means toggled on)
        self.drum_mute_toggle: Set[int] = set()  # Which drums are manually muted
        self.drum_solo_toggle: Set[int] = set()  # Which drums are manually soloed
        self.pattern_drum_mute_state: Dict[int, List[bool]] = {}  # Per-pattern mute state
        self.pattern_drum_solo_state: Dict[int, List[bool]] = {}  # Per-pattern solo state

        # Humanize settings per-pattern
        self.pattern_humanize_enabled: Dict[int, bool] = {}  # Track ON/OFF per pattern
        self.pattern_humanize_velocity_amount: Dict[int, float] = {}  # Track velocity amount per pattern

        # Humanize utility instance
        self.humanizer = Humanizer()

        # Fill pattern management (per-pattern assignment)
        self.pattern_fill_patterns: Dict[int, Optional[int]] = {i: None for i in range(1, 65)}  # pattern_num -> fill_id
        self._fill_in_progress: bool = False  # Currently playing a fill
        self._current_fill_id: Optional[int] = None  # Which fill is playing
        self._cached_expanded_fill: Optional[List] = None  # Cache expanded fill pattern for performance
        self._cached_fill_step_count: int = 0  # Track what step count the cache was made for

        # Randomization strategy cycling
        self._randomization_strategies = [
            "Light Random (30%)",
            "Medium Random (50%)",
            "Heavy Random (70%)",
            "Quarter Beat",
            "Mixed 70/30",
            "Mixed 50/50",
            "Full Fill"
        ]
        self._current_random_strategy_idx = 0

        # Pre-compute MIDI notes for all drums (avoid dict lookups during playback)
        self._drum_midi_notes = {}
        for drum_name in self.DRUM_SOUNDS:
            if drum_name in DRUM_PRESETS:
                self._drum_midi_notes[drum_name] = DRUM_PRESETS[drum_name]["midi_note"]

        # Store Acordes components for integration
        self.midi_handler = midi_handler
        self.config_manager = config_manager if config_manager is not None else SimpleConfigManager(bpm=120)
        self.synth_engine = synth_engine  # Shared Acordes SynthEngine (always used for drum synthesis)

        # Create drum voice manager for monophonic drum synthesis
        self.drum_voice_manager = DrumVoiceManager(self.synth_engine)

        # Initialize sequencer engine with optional BPM callback for Acordes integration
        # If config_manager was provided (Acordes), pass a callback so it syncs with other modes
        bpm_callback = None
        if config_manager is not None:
            bpm_callback = lambda: self.config_manager.get_bpm()

        self.sequencer = SequencerEngine(
            self.synth_engine,
            self.config_manager,
            num_steps=16,
            bpm_callback=bpm_callback
        )

        # Set up sequencer callback for UI updates
        self.sequencer.set_step_callback(self._on_sequencer_step)

        # Update timer handles
        self._update_timer_handle: Optional[object] = None
        self._auto_save_timer_handle: Optional[object] = None

        # Playhead step (-1 = no playhead shown)
        self.playhead_step: int = -1

    def compose(self):
        """Compose the drum machine layout."""
        yield HeaderWidget(title="TAMBOR", subtitle="TR-909 Drum Sequencer")

        self.control_panel = ControlPanel()
        yield self.control_panel

        for drum_idx, drum_name in enumerate(self.DRUM_SOUNDS):
            # Pass pattern data to DrumRow so cells are initialized correctly
            # Pattern may be None if not yet loaded from disk
            pattern_data = None
            if self.patterns[self.current_pattern] is not None and drum_idx < len(self.patterns[self.current_pattern]):
                pattern_data = self.patterns[self.current_pattern][drum_idx]
            row = DrumRow(drum_name, drum_idx, num_steps=self.current_step_count, pattern_data=pattern_data)
            self.drum_rows.append(row)
            yield row

    def on_mount(self):
        """Initialize the sequencer on mount."""
        # Load last edited pattern from previous session
        last_pattern = self._load_last_pattern()
        if last_pattern and 1 <= last_pattern <= 64:
            self.current_pattern = last_pattern

        # Load initial pattern from disk on app startup (force_reload=True)
        self._load_current_pattern(force_reload=True)

        # Schedule grid rebuild after initial layout is complete
        # This ensures cells render properly in Textual's widget lifecycle
        def rebuild_grid_delayed():
            if len(self.drum_rows) > 0:
                self._rebuild_grid()
                # Restore mute/solo button states after grid rebuild
                # (grid rebuild recreates DrumRow widgets, losing button state)
                self._update_all_drum_row_displays()
                # Clear dirty flag since rebuild on startup is not a user change
                self.pattern_dirty.discard(self.current_pattern)
                # Update control panel to remove asterisk
                if self.control_panel:
                    self.control_panel.update_pattern(self.current_pattern, is_dirty=False)

        # Use call_later to ensure layout is complete before rebuilding
        self.call_later(rebuild_grid_delayed)

        self._highlight_cursor()

        # Pre-render all drum sounds in a background thread to avoid blocking UI
        threading.Thread(target=self._preload_drums, daemon=True).start()

        # Start the update timer for sequencer playback
        # Update 10x per second (100ms interval) to check for step advancement
        self._update_timer_handle = self.set_interval(
            0.05,  # 50ms interval for better precision and smoother playback
            self._update_sequencer
        )

        # Start the auto-save timer (5-second interval)
        self._auto_save_timer_handle = self.set_interval(
            5.0,  # 5-second interval
            self._auto_save_periodic
        )

    def on_unmount(self):
        """Clean up when leaving Tambor mode."""
        # Stop playback if playing
        if self.sequencer.is_playing:
            self.action_toggle_playback()

        # Cancel update timers to prevent background playback
        # Note: set_interval() returns a Timer object, so we call .stop() on it
        if self._update_timer_handle is not None:
            self._update_timer_handle.stop()
            self._update_timer_handle = None

        if self._auto_save_timer_handle is not None:
            self._auto_save_timer_handle.stop()
            self._auto_save_timer_handle = None

        # Save any unsaved changes immediately on mode exit
        self._auto_save_periodic()

        # Save the current pattern number for next session
        self._save_last_pattern(self.current_pattern)

        # Shutdown the background pattern saver (waits for pending saves to complete)
        self._pattern_saver.shutdown()

        # Silence all drums
        self.drum_voice_manager.all_notes_off()

    def _preload_drums(self):
        """Pre-render all drum sounds (runs in background thread)."""
        # Only preload if synth engine supports it (local DrumSynth only, not Acordes SynthEngine)
        if not hasattr(self.synth_engine, 'preload'):
            return

        for drum_name, preset in DRUM_PRESETS.items():
            midi_note = preset["midi_note"]
            synth_params = preset["synth_params"]
            self.synth_engine.preload(midi_note, synth_params)

    def action_move_drum_up(self):
        """Move cursor up through drums."""
        new_drum = self.cursor_drum - 1
        if 0 <= new_drum < len(self.DRUM_SOUNDS):
            self.cursor_drum = new_drum
            # Keep current focus area (grid, mute, or solo) when changing drums
            self._highlight_cursor()

    def action_move_drum_down(self):
        """Move cursor down through drums."""
        new_drum = self.cursor_drum + 1
        if 0 <= new_drum < len(self.DRUM_SOUNDS):
            self.cursor_drum = new_drum
            # Keep current focus area (grid, mute, or solo) when changing drums
            self._highlight_cursor()

    def action_move_step_left(self):
        """Move cursor left (← key) - handles both grid navigation and button focus."""
        if self.cursor_focus == "grid":
            if self.cursor_step > 0:
                # Move left in grid
                self.cursor_step -= 1
            else:
                # At leftmost column (step 0), move to solo button
                self.cursor_focus = "solo"
        elif self.cursor_focus == "solo":
            # From solo, move to mute
            self.cursor_focus = "mute"
        elif self.cursor_focus == "mute":
            # Already at mute, stay here
            pass

        self._highlight_cursor()

    def action_move_step_right(self):
        """Move cursor right (→ key) - handles both grid navigation and button focus."""
        if self.cursor_focus == "grid":
            if self.cursor_step < self.current_step_count - 1:
                # Move right in grid
                self.cursor_step += 1
            # At rightmost column, stay in grid (don't move to buttons)
        elif self.cursor_focus == "mute":
            # From mute, move to solo
            self.cursor_focus = "solo"
        elif self.cursor_focus == "solo":
            # From solo, move back to grid at step 0
            self.cursor_focus = "grid"
            self.cursor_step = 0

        self._highlight_cursor()

    def action_toggle_step(self):
        """Toggle the current focused element - step cell, mute button, or solo button."""
        if self.cursor_focus == "grid":
            # Toggle grid step
            if 0 <= self.cursor_drum < len(self.drum_rows):
                # Toggle the UI cell
                self.drum_rows[self.cursor_drum].toggle_step(self.cursor_step)

                # Also toggle in the pattern dict
                pattern = self.patterns[self.current_pattern]
                if pattern and self.cursor_drum < len(pattern) and self.cursor_step < len(pattern[self.cursor_drum]):
                    step_data = pattern[self.cursor_drum][self.cursor_step]
                    step_data["active"] = not step_data["active"]
                    # Mark pattern as dirty - will be auto-saved in 5 seconds
                    # (don't save immediately so asterisk is visible to user)
                    self._mark_pattern_dirty(self.current_pattern)
        elif self.cursor_focus == "mute":
            # Toggle mute for current drum
            self.action_toggle_mute()
        elif self.cursor_focus == "solo":
            # Toggle solo for current drum
            self.action_toggle_solo()

    def action_toggle_playback(self):
        """Toggle play/stop (space bar).

        - If stopped, start playback from step 0
        - If playing, stop playback and reset to step 0
        """
        if self.playback_state == "STOPPED":
            self.playback_state = "PLAYING"
            self.sequencer.stop()  # Reset to step 0
            self.sequencer.start()  # Then start playback
            # Trigger the initial step (step 0) immediately so it plays on startup
            self._trigger_active_drums_for_step(0)
            # Update playhead to show step 0 immediately
            self._update_playhead(0)
        else:
            self.playback_state = "STOPPED"
            self.sequencer.stop()  # Stop and reset to step 0
            self._clear_playhead()

        if self.control_panel:
            self.control_panel.update_state(self.playback_state)
            self.control_panel.update_step(0)

    def action_stop_playback(self):
        """Stop playback explicitly (S key).

        Same as space bar - always stops and resets to step 0.
        """
        self.playback_state = "STOPPED"
        self.sequencer.stop()
        self._clear_playhead()
        if self.control_panel:
            self.control_panel.update_state(self.playback_state)
            self.control_panel.update_step(0)

    def _select_pattern(self, pattern: int):
        """Select a pattern (1-64).

        Args:
            pattern: Pattern number (1-64)
        """
        if 1 <= pattern <= 64:
            # Auto-save current pattern before switching
            self._auto_save_current_pattern()

            self.current_pattern = pattern
            # Load pattern from memory or disk
            self._load_current_pattern()

            # Check if pattern is empty - if so, always use 16 steps
            if not self._pattern_has_data(self.patterns[pattern]):
                self.current_step_count = 16
                self.pattern_step_counts[pattern] = 16
            else:
                # Use saved step count for patterns with data
                self.current_step_count = self.pattern_step_counts[pattern]

            # Update sequencer with new step count
            self.sequencer.num_steps = self.current_step_count

            if self.control_panel:
                # Check if new pattern has unsaved changes
                is_dirty = self.current_pattern in self.pattern_dirty
                self.control_panel.update_pattern(self.current_pattern, is_dirty=is_dirty)
                self.control_panel.update_step_count(self.current_step_count)

    def action_open_pattern_selector(self):
        """Open pattern selector as modal screen (N key)."""
        # Get saved patterns (only those with actual data, not cleared patterns)
        saved_patterns = set()
        for pnum in range(1, 65):
            if self.pattern_manager.pattern_exists(pnum):
                # Check if pattern has any active steps
                pattern = self.patterns.get(pnum)
                if pattern is None:
                    # Load pattern from disk to check if it has data
                    pattern_data = self.pattern_manager.load_pattern(pnum, drum_names=self.DRUM_SOUNDS)
                    # Extract the pattern list from the loaded data
                    if pattern_data and "pattern_data" in pattern_data:
                        pattern = pattern_data["pattern_data"]

                # Check if pattern has any active steps
                if pattern and self._pattern_has_data(pattern):
                    saved_patterns.add(pnum)

        # Push pattern selector screen as modal
        selector_screen = PatternSelectorScreen(
            current_pattern=self.current_pattern,
            on_select=self._on_pattern_selected,
            on_delete=self._on_pattern_deleted,
            saved_patterns=saved_patterns,
        )
        self.app.push_screen(selector_screen)

    def _pattern_has_data(self, pattern: List) -> bool:
        """Check if a pattern has any active steps."""
        for drum in pattern:
            for step in drum:
                if step.get("active", False):
                    return True
        return False

    def _on_pattern_selected(self, pattern_num: int):
        """Callback when user selects a pattern from selector."""
        self._select_pattern(pattern_num)

    def _on_pattern_deleted(self, pattern_num: int):
        """Callback when user clears a pattern from selector."""
        # Save current pattern data to undo stack (for undo functionality)
        if self.patterns[pattern_num] is not None:
            self.undo_stack.append((pattern_num, self.patterns[pattern_num].copy()))

        # Reset to default: 16 steps
        self.pattern_step_counts[pattern_num] = 16

        # Create empty pattern with 16 steps and save to disk
        empty_pattern = self._create_empty_pattern(16)
        self.patterns[pattern_num] = empty_pattern

        # Save empty pattern to disk
        self.pattern_manager.save_pattern(
            pattern_num,
            empty_pattern,
            drum_names=self.DRUM_SOUNDS,
            bpm=self.pattern_bpms[pattern_num],
            num_steps=16,
            pre_scale=str(self.current_pre_scale.value)
        )

        # If this is the current pattern, update UI
        if pattern_num == self.current_pattern:
            # Reset step count display
            self.current_step_count = 16
            self.sequencer.num_steps = 16

            # Rebuild grid with 16 steps
            self._rebuild_grid()

            # Update control panel
            self.control_panel.update_step_count(16)

    def action_clear_pattern(self):
        """Clear all active steps for the currently selected drum (C key)."""
        pattern = self.patterns[self.current_pattern]
        if pattern is None:
            return

        # Clear only the selected drum's steps
        drum_idx = self.cursor_drum
        if drum_idx < len(pattern):
            for step_idx in range(len(pattern[drum_idx])):
                pattern[drum_idx][step_idx]["active"] = False

            # Update the UI for the selected drum row
            self.drum_rows[drum_idx].set_pattern(pattern[drum_idx])

        # Mark as dirty and auto-save
        self._mark_pattern_dirty(self.current_pattern)
        self._auto_save_current_pattern()

    def action_undo_delete(self):
        """Undo the last deleted pattern (Ctrl+Z key)."""
        if not self.undo_stack:
            return  # No undo history

        # Pop the last deleted pattern from undo stack
        pattern_num, pattern_data = self.undo_stack.pop()

        # Restore pattern to memory
        self.patterns[pattern_num] = pattern_data.copy()

        # Save pattern back to disk
        self.pattern_manager.save_pattern(
            pattern_num,
            pattern_data,
            drum_names=self.DRUM_SOUNDS,
            bpm=self.pattern_bpms[pattern_num],
            num_steps=self.pattern_step_counts[pattern_num],
            pre_scale=str(self.current_pre_scale.value)
        )

        # If this is the current pattern, reload it to UI
        if pattern_num == self.current_pattern:
            self._load_current_pattern(force_reload=True)

    def action_increase_step_count(self):
        """Increase step count for current pattern (+ key)."""
        new_count = min(32, self.current_step_count + 1)
        if new_count != self.current_step_count:
            self.current_step_count = new_count
            self.pattern_step_counts[self.current_pattern] = new_count
            self._mark_pattern_dirty(self.current_pattern)
            self.sequencer.num_steps = new_count
            self._rebuild_grid()
            # Immediately save so step count is persisted
            self._auto_save_current_pattern()

    def action_decrease_step_count(self):
        """Decrease step count for current pattern (- key)."""
        new_count = max(2, self.current_step_count - 1)
        if new_count != self.current_step_count:
            self.current_step_count = new_count
            self.pattern_step_counts[self.current_pattern] = new_count
            self._mark_pattern_dirty(self.current_pattern)
            self.sequencer.num_steps = new_count
            self._rebuild_grid()
            # Immediately save so step count is persisted
            self._auto_save_current_pattern()

    def action_edit_drum(self):
        """Open drum editor for currently selected drum (E key)."""
        drum_idx = self.cursor_drum
        if drum_idx < 0 or drum_idx >= len(self.DRUM_SOUNDS):
            return

        drum_name = self.DRUM_SOUNDS[drum_idx]

        # Get current drum presets (base presets + any pattern-specific overrides)
        base_preset = DRUM_PRESETS.get(drum_name, {})
        synth_params = base_preset.get("synth_params", {}).copy()

        # Apply pattern-local overrides if they exist
        pattern = self.patterns[self.current_pattern]
        if pattern is not None and hasattr(self, 'pattern_drum_overrides'):
            overrides = self.pattern_drum_overrides.get(self.current_pattern, {})
            if drum_name in overrides:
                synth_params.update(overrides[drum_name])

        # Save current mute state for restoration when editor closes
        mute_state_before = self.sequencer.save_mute_state()

        # Solo the edited drum during editing (mute all others if sequencer is playing)
        if self.sequencer.is_playing:
            edited_midi_note = base_preset.get("midi_note", 60)
            for other_drum in self.DRUM_SOUNDS:
                other_preset = DRUM_PRESETS.get(other_drum, {})
                other_midi = other_preset.get("midi_note", 60)
                if other_midi != edited_midi_note:
                    self.sequencer.mute_drum(other_midi)
                else:
                    self.sequencer.unmute_drum(other_midi)  # Ensure edited drum is unmuted

        # Create close callback that restores mute state
        def _on_editor_close():
            self.sequencer.restore_mute_state(mute_state_before)

        # Open drum editor modal with sequencer for preview functionality
        editor_screen = DrumEditorScreen(
            drum_name=drum_name,
            synth_params=synth_params,
            on_apply=lambda params: self._on_drum_editor_applied(drum_name, params),
            sequencer=self.sequencer,
            on_close=_on_editor_close,
            on_parameter_change=lambda params: self.update_drum_override_during_edit(drum_name, params)
        )
        self.app.push_screen(editor_screen)

    def _on_drum_editor_applied(self, drum_name: str, synth_params: Dict[str, Any]):
        """Callback when drum editor applies changes."""
        # Initialize pattern_drum_overrides if needed
        if not hasattr(self, 'pattern_drum_overrides'):
            self.pattern_drum_overrides = {}

        # Store overrides for current pattern
        if self.current_pattern not in self.pattern_drum_overrides:
            self.pattern_drum_overrides[self.current_pattern] = {}

        self.pattern_drum_overrides[self.current_pattern][drum_name] = synth_params

        # Mark pattern as dirty
        self._mark_pattern_dirty(self.current_pattern)

        # Auto-save immediately
        self._auto_save_current_pattern()

    def update_drum_override_during_edit(self, drum_name: str, synth_params: Dict[str, Any]):
        """Update drum overrides in real-time while editing (for live feedback during playback)."""
        # Initialize pattern_drum_overrides if needed
        if not hasattr(self, 'pattern_drum_overrides'):
            self.pattern_drum_overrides = {}

        # Store overrides for current pattern
        if self.current_pattern not in self.pattern_drum_overrides:
            self.pattern_drum_overrides[self.current_pattern] = {}

        self.pattern_drum_overrides[self.current_pattern][drum_name] = synth_params

    def action_select_pattern_1(self):
        """Select pattern 1 (quick access)."""
        self._select_pattern(1)

    def action_select_pattern_2(self):
        """Select pattern 2 (quick access)."""
        self._select_pattern(2)

    def action_select_pattern_3(self):
        """Select pattern 3 (quick access)."""
        self._select_pattern(3)

    def action_select_pattern_4(self):
        """Select pattern 4 (quick access)."""
        self._select_pattern(4)

    def action_cycle_pre_scale(self):
        """Cycle through available PRE-SCALE values."""
        self.pre_scale_index = (self.pre_scale_index + 1) % len(self.pre_scale_values)
        self.current_pre_scale = self.pre_scale_values[self.pre_scale_index]
        self._update_control_panel_pre_scale()

    def action_toggle_mute(self):
        """Toggle mute for currently selected drum (M key)."""
        drum_idx = self.cursor_drum
        if drum_idx < 0 or drum_idx >= len(self.DRUM_SOUNDS):
            return

        drum_name = self.DRUM_SOUNDS[drum_idx]
        midi_note = DRUM_PRESETS.get(drum_name, {}).get("midi_note", 60)

        if drum_idx in self.drum_mute_toggle:
            # Remove from manual mute
            self.drum_mute_toggle.remove(drum_idx)
            self.sequencer.unmute_drum(midi_note)
        else:
            # Add to manual mute
            self.drum_mute_toggle.add(drum_idx)
            self.sequencer.mute_drum(midi_note)

        # Update display for this drum row
        self._update_drum_row_display(drum_idx)

        # Mark pattern dirty for persistence
        self._mark_pattern_dirty(self.current_pattern)

    def action_toggle_solo(self):
        """Toggle solo for currently selected drum (Alt+S key)."""
        drum_idx = self.cursor_drum
        if drum_idx < 0 or drum_idx >= len(self.DRUM_SOUNDS):
            return

        if drum_idx in self.drum_solo_toggle:
            # Remove from solo
            self.drum_solo_toggle.remove(drum_idx)
        else:
            # Add to solo
            self.drum_solo_toggle.add(drum_idx)

        # Recalculate mute state based on solo toggles and manual mutes
        self._update_drum_mute_state_from_solo()

        # Update all drum row displays since solo affects all drums
        self._update_all_drum_row_displays()

        # Mark pattern dirty for persistence
        self._mark_pattern_dirty(self.current_pattern)

    def action_toggle_humanize(self):
        """Toggle humanize for current pattern (H key)."""
        pattern_num = self.current_pattern
        current_enabled = self._get_pattern_humanize_enabled(pattern_num)

        # Toggle enabled state, keeping current velocity amount
        self._set_pattern_humanize(
            pattern_num,
            enabled=not current_enabled,
            velocity_amount=self._get_pattern_humanize_velocity_amount(pattern_num)
        )

        # Update control panel to show new humanize status
        self._update_control_panel_humanize()

        # Mark pattern dirty for persistence
        self._mark_pattern_dirty(pattern_num)

    def action_randomize_drum(self):
        """Randomize steps for current drum with cycling strategies (R key)."""
        drum_idx = self.cursor_drum
        pattern_num = self.current_pattern

        # Get current strategy and cycle to next
        strategy = self._randomization_strategies[self._current_random_strategy_idx]
        self._current_random_strategy_idx = (self._current_random_strategy_idx + 1) % len(self._randomization_strategies)

        # Get pattern and apply randomization
        pattern = self.patterns[pattern_num]
        if pattern and drum_idx < len(pattern):
            num_steps = self.current_step_count
            randomized_pattern = self._randomize_drum_pattern(pattern[drum_idx], num_steps, strategy)
            pattern[drum_idx] = randomized_pattern

            # Update UI
            if drum_idx < len(self.drum_rows):
                self.drum_rows[drum_idx].set_pattern(randomized_pattern)

            # Mark pattern dirty for auto-save
            self._mark_pattern_dirty(pattern_num)

    def _randomize_drum_pattern(self, pattern: list, num_steps: int, strategy: str) -> list:
        """Generate randomized drum pattern based on strategy.

        Args:
            pattern: Original pattern (will be replaced)
            num_steps: Number of steps in pattern
            strategy: Randomization strategy name

        Returns:
            New randomized pattern
        """
        import random

        # Clear pattern - create empty steps
        new_pattern = [
            {"active": False, "velocity": 100, "note_length": 0.5}
            for _ in range(num_steps)
        ]

        # Generate quarter beat positions (every 4 steps: 0, 4, 8, 12, 16, 20, 28...)
        quarter_beat_positions = [i for i in range(0, num_steps, 4)]

        if strategy == "Light Random (30%)":
            # 30% of all steps randomly
            num_to_fill = max(1, int(num_steps * 0.3))
            positions = random.sample(range(num_steps), min(num_to_fill, num_steps))
            for pos in positions:
                new_pattern[pos]["active"] = True
                new_pattern[pos]["velocity"] = random.randint(80, 120)

        elif strategy == "Medium Random (50%)":
            # 50% of all steps randomly
            num_to_fill = max(1, int(num_steps * 0.5))
            positions = random.sample(range(num_steps), min(num_to_fill, num_steps))
            for pos in positions:
                new_pattern[pos]["active"] = True
                new_pattern[pos]["velocity"] = random.randint(80, 120)

        elif strategy == "Heavy Random (70%)":
            # 70% of all steps randomly
            num_to_fill = max(1, int(num_steps * 0.7))
            positions = random.sample(range(num_steps), min(num_to_fill, num_steps))
            for pos in positions:
                new_pattern[pos]["active"] = True
                new_pattern[pos]["velocity"] = random.randint(80, 120)

        elif strategy == "Quarter Beat":
            # Just the predefined quarter beat (1, 5, 9, 13...)
            for pos in quarter_beat_positions:
                new_pattern[pos]["active"] = True
                new_pattern[pos]["velocity"] = 100

        elif strategy == "Mixed 70/30":
            # 30% predefined beats + 70% random
            # First add quarter beats
            for pos in quarter_beat_positions:
                new_pattern[pos]["active"] = True
                new_pattern[pos]["velocity"] = 100

            # Then add 70% random to remaining steps
            remaining_positions = [i for i in range(num_steps) if i not in quarter_beat_positions]
            num_random = max(0, int(len(remaining_positions) * 0.7))
            if remaining_positions and num_random > 0:
                random_positions = random.sample(remaining_positions, min(num_random, len(remaining_positions)))
                for pos in random_positions:
                    new_pattern[pos]["active"] = True
                    new_pattern[pos]["velocity"] = random.randint(80, 120)

        elif strategy == "Mixed 50/50":
            # 50% predefined beats + 50% random
            # First add quarter beats
            for pos in quarter_beat_positions:
                new_pattern[pos]["active"] = True
                new_pattern[pos]["velocity"] = 100

            # Then add 50% random to remaining steps
            remaining_positions = [i for i in range(num_steps) if i not in quarter_beat_positions]
            num_random = max(0, int(len(remaining_positions) * 0.5))
            if remaining_positions and num_random > 0:
                random_positions = random.sample(remaining_positions, min(num_random, len(remaining_positions)))
                for pos in random_positions:
                    new_pattern[pos]["active"] = True
                    new_pattern[pos]["velocity"] = random.randint(80, 120)

        elif strategy == "Full Fill":
            # All steps active
            for i in range(num_steps):
                new_pattern[i]["active"] = True
                new_pattern[i]["velocity"] = random.randint(90, 110)

        return new_pattern

    def action_open_fill_selector(self):
        """Open fill pattern selector (F key)."""
        pattern_num = self.current_pattern
        current_fill_id = self.pattern_fill_patterns.get(pattern_num)

        # Create fill selector screen with callback
        fill_screen = FillSelectorScreen(
            current_fill_id=current_fill_id,
            on_fill_selected=self._on_fill_selected
        )
        self.app.push_screen(fill_screen)

    def _on_fill_selected(self, fill_id: Optional[int]):
        """Callback when user selects a fill pattern."""
        pattern_num = self.current_pattern
        self.pattern_fill_patterns[pattern_num] = fill_id
        self._mark_pattern_dirty(pattern_num)

        # Update UI to show selected fill
        self._update_control_panel_fill()

        # Auto-save will handle persistence in the next 5-second interval

    def _update_drum_mute_state_from_solo(self):
        """Update sequencer mute state based on solo toggles and manual mutes.

        Logic:
        - If any drum is soloed, mute everything except soloed drums and manually unmuted drums
        - If no drums are soloed, respect only manual mutes
        """
        if self.drum_solo_toggle:
            # Solo is active: mute everything EXCEPT soloed drums and manually unmuted drums
            for drum_idx, drum_name in enumerate(self.DRUM_SOUNDS):
                midi_note = DRUM_PRESETS.get(drum_name, {}).get("midi_note", 60)
                is_soloed = drum_idx in self.drum_solo_toggle
                is_manually_muted = drum_idx in self.drum_mute_toggle

                if is_manually_muted:
                    # Explicit mute overrides everything
                    self.sequencer.mute_drum(midi_note)
                elif is_soloed:
                    # Soloed drums play
                    self.sequencer.unmute_drum(midi_note)
                else:
                    # Not soloed and not explicitly unmuted, so mute
                    self.sequencer.mute_drum(midi_note)
        else:
            # Solo not active: respect only manual mutes
            for drum_idx, drum_name in enumerate(self.DRUM_SOUNDS):
                midi_note = DRUM_PRESETS.get(drum_name, {}).get("midi_note", 60)
                is_manually_muted = drum_idx in self.drum_mute_toggle

                if is_manually_muted:
                    self.sequencer.mute_drum(midi_note)
                else:
                    self.sequencer.unmute_drum(midi_note)

    def _update_drum_row_display(self, drum_idx: int):
        """Update the mute/solo display for a specific drum row."""
        if 0 <= drum_idx < len(self.drum_rows):
            is_muted = drum_idx in self.drum_mute_toggle
            is_soloed = drum_idx in self.drum_solo_toggle
            self.drum_rows[drum_idx].update_mute_solo_display(is_muted, is_soloed)

    def _update_all_drum_row_displays(self):
        """Update mute/solo displays for all drum rows."""
        for drum_idx in range(len(self.drum_rows)):
            self._update_drum_row_display(drum_idx)

    def _get_pattern_humanize_enabled(self, pattern_num: int) -> bool:
        """Get humanize enabled state for pattern."""
        return self.pattern_humanize_enabled.get(pattern_num, False)

    def _get_pattern_humanize_velocity_amount(self, pattern_num: int) -> float:
        """Get humanize velocity amount for pattern (0.0-0.3)."""
        return self.pattern_humanize_velocity_amount.get(pattern_num, 0.15)

    def _set_pattern_humanize(
        self,
        pattern_num: int,
        enabled: bool,
        velocity_amount: float = 0.15
    ):
        """Set humanize settings for pattern."""
        self.pattern_humanize_enabled[pattern_num] = enabled
        # Clamp velocity_amount to valid range
        self.pattern_humanize_velocity_amount[pattern_num] = max(0.0, min(0.3, velocity_amount))

    def _update_control_panel_humanize(self):
        """Update control panel to show humanize status."""
        if self.control_panel:
            enabled = self._get_pattern_humanize_enabled(self.current_pattern)
            if enabled:
                velocity_pct = self._get_pattern_humanize_velocity_amount(self.current_pattern) * 100
                status = f"Humanize: ON ({velocity_pct:.0f}%)"
            else:
                status = "Humanize: OFF"
            self.control_panel.update_humanize_info(status)

    def _update_control_panel_fill(self):
        """Update control panel to show current fill assignment."""
        if self.control_panel:
            fill_id = self.pattern_fill_patterns.get(self.current_pattern)
            if fill_id is not None:
                status = f"Fill: {fill_id}"
            else:
                status = "Fill: None"
            self.control_panel.update_fill_info(status)

    def _update_focus_label(self):
        """Update the focus info label based on current cursor position."""
        if 0 <= self.cursor_drum < len(self.DRUM_SOUNDS):
            drum_name = self.DRUM_SOUNDS[self.cursor_drum]

            # Generate focus info based on cursor_focus
            if self.cursor_focus == "grid":
                focus_info = f"Step {self.cursor_step + 1:02d}"
            elif self.cursor_focus == "mute":
                focus_info = "Mute"
            elif self.cursor_focus == "solo":
                focus_info = "Solo"
            else:
                focus_info = "Unknown"

            # Update control panel
            if self.control_panel:
                self.control_panel.update_focus_info(drum_name, focus_info)

    def _highlight_cursor(self):
        """Highlight the current cursor position - handles grid cells and buttons."""
        for drum_idx, row in enumerate(self.drum_rows):
            # Highlight selected drum row with yellow
            if drum_idx == self.cursor_drum:
                row.add_class("selected")
            else:
                row.remove_class("selected")

            # Update grid cell focus
            for step_idx, cell in enumerate(row.cells):
                is_focused = (drum_idx == self.cursor_drum and step_idx == self.cursor_step and self.cursor_focus == "grid")
                if is_focused:
                    cell.add_class("focused")
                else:
                    cell.remove_class("focused")

            # Update button focus
            if drum_idx == self.cursor_drum:
                if self.cursor_focus == "mute":
                    row.set_mute_button_focus(True)
                elif self.cursor_focus == "solo":
                    row.set_solo_button_focus(True)
                else:
                    row.clear_button_focus()
            else:
                row.clear_button_focus()

        # Update focus info label
        self._update_focus_label()

    def _mark_pattern_dirty(self, pattern_num: int):
        """Mark a pattern as needing to be saved."""
        self.pattern_dirty.add(pattern_num)
        # Update control panel to show asterisk if this is the current pattern
        if pattern_num == self.current_pattern and self.control_panel:
            self.control_panel.update_pattern(self.current_pattern, is_dirty=True)

    def _auto_save_current_pattern(self):
        """Immediately auto-save the current pattern to disk."""
        pattern = self.patterns[self.current_pattern]
        if pattern is None:
            return

        bpm = self.pattern_bpms[self.current_pattern]
        num_steps = self.pattern_step_counts[self.current_pattern]
        pre_scale = str(self.current_pre_scale.value)

        # Build mute/solo state as lists (one bool per drum)
        mute_state = [drum_idx in self.drum_mute_toggle for drum_idx in range(len(self.DRUM_SOUNDS))]
        solo_state = [drum_idx in self.drum_solo_toggle for drum_idx in range(len(self.DRUM_SOUNDS))]

        # Get drum overrides if they exist
        drum_overrides = None
        if hasattr(self, 'pattern_drum_overrides') and self.current_pattern in self.pattern_drum_overrides:
            drum_overrides = self.pattern_drum_overrides[self.current_pattern]

        # Get humanize settings for current pattern
        humanize_enabled = self._get_pattern_humanize_enabled(self.current_pattern)
        humanize_velocity_amount = self._get_pattern_humanize_velocity_amount(self.current_pattern)

        # Get fill pattern assignment for current pattern
        fill_pattern_id = self.pattern_fill_patterns.get(self.current_pattern)

        self.pattern_manager.save_pattern(
            self.current_pattern,
            pattern,
            self.DRUM_SOUNDS,
            bpm=bpm,
            num_steps=num_steps,
            pre_scale=pre_scale,
            mute_state=mute_state if any(mute_state) else None,
            solo_state=solo_state if any(solo_state) else None,
            drum_overrides=drum_overrides,
            humanize_enabled=humanize_enabled,
            humanize_velocity_amount=humanize_velocity_amount,
            fill_pattern_id=fill_pattern_id,
        )

        # Mark as clean after saving
        self.pattern_dirty.discard(self.current_pattern)
        # Remove asterisk from control panel
        if self.control_panel:
            self.control_panel.update_pattern(self.current_pattern, is_dirty=False)

    def _auto_save_periodic(self):
        """Periodically auto-save all dirty patterns (runs every 5 seconds) - non-blocking."""
        for pattern_num in list(self.pattern_dirty):
            if pattern_num in self.patterns and self.patterns[pattern_num] is not None:
                pattern = self.patterns[pattern_num]
                bpm = self.pattern_bpms[pattern_num]
                num_steps = self.pattern_step_counts[pattern_num]
                pre_scale = str(self.current_pre_scale.value)

                # Build mute/solo state as lists (one bool per drum)
                # Only use mute/solo state if current pattern matches (since toggles are per-current-pattern)
                mute_state = None
                solo_state = None
                if pattern_num == self.current_pattern:
                    mute_state = [drum_idx in self.drum_mute_toggle for drum_idx in range(len(self.DRUM_SOUNDS))]
                    solo_state = [drum_idx in self.drum_solo_toggle for drum_idx in range(len(self.DRUM_SOUNDS))]
                    mute_state = mute_state if any(mute_state) else None
                    solo_state = solo_state if any(solo_state) else None

                # Get drum overrides if they exist
                drum_overrides = None
                if hasattr(self, 'pattern_drum_overrides') and pattern_num in self.pattern_drum_overrides:
                    drum_overrides = self.pattern_drum_overrides[pattern_num]

                # Get humanize settings for this pattern
                humanize_enabled = self._get_pattern_humanize_enabled(pattern_num)
                humanize_velocity_amount = self._get_pattern_humanize_velocity_amount(pattern_num)

                # Get fill pattern assignment for this pattern
                fill_pattern_id = self.pattern_fill_patterns.get(pattern_num)

                # Queue save in background (non-blocking) instead of saving directly
                save_kwargs = {
                    "bpm": bpm,
                    "num_steps": num_steps,
                    "pre_scale": pre_scale,
                    "mute_state": mute_state,
                    "solo_state": solo_state,
                    "drum_overrides": drum_overrides,
                    "humanize_enabled": humanize_enabled,
                    "humanize_velocity_amount": humanize_velocity_amount,
                    "fill_pattern_id": fill_pattern_id,
                }
                self._pattern_saver.queue_save(pattern_num, pattern, self.DRUM_SOUNDS, **save_kwargs)

                # Mark as clean immediately (save is queued but will happen in background)
                self.pattern_dirty.discard(pattern_num)

                # Update control panel to remove asterisk if this is the current pattern
                if pattern_num == self.current_pattern and self.control_panel:
                    self.control_panel.update_pattern(self.current_pattern, is_dirty=False)

    def _rebuild_grid(self):
        """Rebuild the grid when step count changes.

        Destroys old DrumRow widgets and recreates them with new step count.
        """
        # Stop playback if running
        if self.playback_state == "PLAYING":
            self.action_stop_playback()

        # Get current pattern data
        current_pattern_data = self.patterns[self.current_pattern]

        # Recreate pattern with new step count
        new_pattern = self._create_empty_pattern(self.current_step_count)

        # Copy active/velocity/note_length data from old pattern
        if current_pattern_data:
            for drum_idx in range(min(len(current_pattern_data), len(new_pattern))):
                for step_idx in range(min(len(current_pattern_data[drum_idx]), len(new_pattern[drum_idx]))):
                    old_step = current_pattern_data[drum_idx][step_idx]
                    new_pattern[drum_idx][step_idx] = old_step.copy()

        # Update pattern in memory
        self.patterns[self.current_pattern] = new_pattern
        self.pattern_step_counts[self.current_pattern] = self.current_step_count
        self._mark_pattern_dirty(self.current_pattern)

        # Destroy old drum rows (only if app is running)
        try:
            for row in self.drum_rows:
                row.remove()
        except Exception:
            pass  # Ignore errors if not in app context (e.g., during tests)
        self.drum_rows.clear()

        # Recreate drum rows with new step count and mount them
        for drum_idx, drum_name in enumerate(self.DRUM_SOUNDS):
            # Pass pattern data to DrumRow so cells are initialized correctly during compose()
            row = DrumRow(
                drum_name,
                drum_idx,
                num_steps=self.current_step_count,
                pattern_data=new_pattern[drum_idx] if drum_idx < len(new_pattern) else None
            )
            self.drum_rows.append(row)
            # Mount the row after TamborMode is already mounted
            if self.is_mounted:
                self.mount(row)

        # Clamp cursor position if needed
        self.cursor_step = min(self.cursor_step, self.current_step_count - 1)
        if self.cursor_step < 0:
            self.cursor_step = 0

        # Update control panel
        if self.control_panel:
            self.control_panel.update_step_count(self.current_step_count)

        # Highlight cursor in new grid
        self._highlight_cursor()

        # Force display refresh to ensure grid is visible
        self.refresh()

    def _save_current_pattern(self):
        """Save the current pattern from the UI to memory.

        Note: With dict-based patterns, we update patterns directly when
        toggling steps, so this is now mainly for compatibility. We skip
        saving if the pattern is already in dict format.
        """
        # Check if pattern is already in dict format - if so, don't overwrite
        pattern = self.patterns[self.current_pattern]
        if pattern and len(pattern) > 0 and len(pattern[0]) > 0:
            if isinstance(pattern[0][0], dict):
                # Pattern is already in dict format, don't overwrite
                return

        # Otherwise, save from UI (backward compatibility for bool patterns)
        new_pattern = []
        for row in self.drum_rows:
            new_pattern.append(row.get_pattern())
        self.patterns[self.current_pattern] = new_pattern

    def _load_current_pattern(self, force_reload: bool = False):
        """Load a pattern from memory or disk to the UI.

        Implements lazy loading with disk persistence:
        - First time loading a pattern (None in memory): load from disk if available
        - Pattern already in memory: use in-memory version (unless force_reload=True)
        - Not on disk: create empty pattern

        Args:
            force_reload: If True, always reload from disk (used for app startup)
        """
        pattern_num = self.current_pattern

        # If pattern is in memory and not forcing reload, use it
        if not force_reload and self.patterns[pattern_num] is not None:
            # Pattern already in memory
            pattern = self.patterns[pattern_num]
            old_step_count = self.current_step_count
            self.current_step_count = self.pattern_step_counts[pattern_num]
            self.sequencer.num_steps = self.current_step_count

            # If step count changed, rebuild grid; otherwise just update pattern
            if old_step_count != self.current_step_count:
                self._rebuild_grid()
            else:
                # Same step count - just update cells
                for drum_idx, row in enumerate(self.drum_rows):
                    if drum_idx < len(pattern):
                        row.set_pattern(pattern[drum_idx])
            return

        # Not in memory (or force_reload=True) - try loading from disk
        loaded_data = self.pattern_manager.load_pattern(
            pattern_num,
            self.DRUM_SOUNDS,
            default_num_steps=self.pattern_step_counts[pattern_num],
        )

        if loaded_data is not None:
            # Successfully loaded from disk
            self.patterns[pattern_num] = loaded_data["pattern_data"]
            old_step_count = self.current_step_count
            self.pattern_step_counts[pattern_num] = loaded_data["num_steps"]
            self.pattern_bpms[pattern_num] = loaded_data["bpm"]
            self.current_step_count = loaded_data["num_steps"]
            self.sequencer.num_steps = loaded_data["num_steps"]

            # Load pre_scale if present
            pre_scale_val = loaded_data.get("pre_scale", "4")
            self.current_pre_scale = PreScale(int(pre_scale_val))
            self.pre_scale_index = self.pre_scale_values.index(self.current_pre_scale)

            # If step count changed, rebuild the grid to update cell count
            if old_step_count != self.current_step_count:
                self._rebuild_grid()

            # Load drum overrides if present (from drum editing)
            drum_overrides = loaded_data.get("drum_overrides", {})
            if drum_overrides:
                # Initialize pattern_drum_overrides if needed
                if not hasattr(self, 'pattern_drum_overrides'):
                    self.pattern_drum_overrides = {}
                self.pattern_drum_overrides[pattern_num] = drum_overrides

            # Load mute/solo state if present
            mute_state = loaded_data.get("mute_state", [])
            solo_state = loaded_data.get("solo_state", [])

            # Restore mute/solo toggles from saved state
            self.drum_mute_toggle.clear()
            self.drum_solo_toggle.clear()
            for drum_idx in range(len(self.DRUM_SOUNDS)):
                if drum_idx < len(mute_state) and mute_state[drum_idx]:
                    self.drum_mute_toggle.add(drum_idx)
                if drum_idx < len(solo_state) and solo_state[drum_idx]:
                    self.drum_solo_toggle.add(drum_idx)

            # Apply mute/solo state to sequencer
            self._update_drum_mute_state_from_solo()

            # Load humanize settings if present
            humanize_enabled = loaded_data.get("humanize_enabled", False)
            humanize_velocity_amount = loaded_data.get("humanize_velocity_amount", 0.15)
            self._set_pattern_humanize(pattern_num, humanize_enabled, humanize_velocity_amount)

            # Load fill pattern assignment if present
            fill_pattern_id = loaded_data.get("fill_pattern_id")
            self.pattern_fill_patterns[pattern_num] = fill_pattern_id

            # Update drum row displays
            self._update_all_drum_row_displays()

            # Update humanize status in control panel
            self._update_control_panel_humanize()

            # Update fill info in control panel
            self._update_control_panel_fill()
        else:
            # Create empty pattern and clear mute/solo toggles
            self.patterns[pattern_num] = self._create_empty_pattern(
                self.pattern_step_counts[pattern_num]
            )
            self.drum_mute_toggle.clear()
            self.drum_solo_toggle.clear()
            # Clear all mutes from sequencer for new pattern
            for drum_name in self.DRUM_SOUNDS:
                midi_note = DRUM_PRESETS.get(drum_name, {}).get("midi_note", 60)
                self.sequencer.unmute_drum(midi_note)

            # Initialize humanize settings for new pattern
            self._set_pattern_humanize(pattern_num, False, 0.15)
            self._update_control_panel_humanize()

            # Initialize fill pattern to None for new pattern
            self.pattern_fill_patterns[pattern_num] = None
            self._update_control_panel_fill()

        # Load to UI
        pattern = self.patterns[self.current_pattern]
        for drum_idx, row in enumerate(self.drum_rows):
            if drum_idx < len(pattern):
                row.set_pattern(pattern[drum_idx])

    def _init_pattern(self, pattern_num: int):
        """Initialize a pattern with empty steps. Used before loading from disk."""
        self.patterns[pattern_num] = self._create_empty_pattern(self.pattern_step_counts[pattern_num])

    def _create_empty_pattern(self, num_steps: int = 16) -> list:
        """Create an empty pattern with configurable step count (8 drums x num_steps).

        Args:
            num_steps: Number of steps in pattern (default 16, range 2-32)
        """
        num_steps = max(2, min(32, num_steps))  # Clamp to valid range
        pattern = []
        for drum_idx in range(len(self.DRUM_SOUNDS)):
            drum_pattern = []
            for step in range(num_steps):
                step_data = {
                    "active": False,
                    "velocity": 100,
                    "note_length": 0.5
                }
                drum_pattern.append(step_data)
            pattern.append(drum_pattern)
        return pattern

    def _update_control_panel_pre_scale(self):
        """Update control panel to show PRE-SCALE info."""
        if self.control_panel:
            pre_scale_val = self.current_pre_scale.value
            info = f"{pre_scale_val} steps/beat"
            self.control_panel.update_pre_scale_info(info)

    def _update_sequencer(self):
        """Update the sequencer (called periodically by timer)."""
        # Advance sequencer if playing
        if self.sequencer.update():
            # Step advanced - trigger drums from pattern
            step = self.sequencer.current_step
            self._trigger_active_drums_for_step(step)

    def _trigger_active_drums_for_step(self, step: int):
        """Trigger all active drums for the given step (optimized)."""
        # Check if we're at the last step of the pattern
        if step == self.current_step_count - 1:
            # Last step - check if we should queue a fill for next cycle
            fill_id = self.pattern_fill_patterns.get(self.current_pattern)
            if fill_id is not None and not self._fill_in_progress:
                # Queue the fill to start on next cycle
                self._current_fill_id = fill_id
                self._cached_expanded_fill = None  # Invalidate cache when new fill queued

        # Handle fill lifecycle at step boundaries
        if step == 0:
            if self._fill_in_progress:
                # Fill just completed
                self._fill_in_progress = False
                self._current_fill_id = None
                self._cached_expanded_fill = None
            elif self._current_fill_id is not None:
                # Start queued fill
                self._fill_in_progress = True
                self._cached_expanded_fill = None  # Invalidate cache to rebuild for fill

        # Determine pattern to play - use cached expanded fill if available and still valid
        if self._fill_in_progress and self._current_fill_id is not None:
            # Check if cache is still valid
            if self._cached_expanded_fill is None or self._cached_fill_step_count != self.current_step_count:
                # Cache miss - expand and cache the fill
                if self._current_fill_id in FILL_TEMPLATES:
                    fill_data = FILL_TEMPLATES[self._current_fill_id]
                    base_fill = fill_data.get("pattern", [])
                    self._cached_expanded_fill = expand_fill_to_steps(base_fill, self.current_step_count)
                    self._cached_fill_step_count = self.current_step_count
                else:
                    # Fallback to main pattern if fill not found
                    pattern_to_play = self.patterns[self.current_pattern]
                    self._fill_in_progress = False
                    self._current_fill_id = None
                    self._cached_expanded_fill = None
                    return
            pattern_to_play = self._cached_expanded_fill
        else:
            # Playing main pattern
            pattern_to_play = self.patterns[self.current_pattern]

        # Get humanize settings once per step (not per drum)
        should_humanize = self._get_pattern_humanize_enabled(self.current_pattern)
        humanize_amount = self._get_pattern_humanize_velocity_amount(self.current_pattern) if should_humanize else 0
        pattern_overrides = self.pattern_drum_overrides.get(self.current_pattern, {}) if hasattr(self, 'pattern_drum_overrides') else {}

        # Iterate through all drums and check current pattern
        for drum_idx in range(len(self.DRUM_SOUNDS)):
            # Quick bounds check
            if drum_idx >= len(pattern_to_play) or step >= len(pattern_to_play[drum_idx]):
                continue

            step_data = pattern_to_play[drum_idx][step]

            # Handle both dict and bool formats for backward compatibility
            if isinstance(step_data, dict):
                if not step_data.get("active", False):
                    continue
                velocity = max(0, min(127, step_data.get("velocity", 100)))
                note_length = max(0.0, min(1.0, step_data.get("note_length", 0.5)))
            else:
                if not step_data:
                    continue
                velocity = 100
                note_length = 0.5

            # Get drum info (optimized with pre-computed MIDI notes)
            drum_name = self.DRUM_SOUNDS[drum_idx]
            midi_note = self._drum_midi_notes.get(drum_name)
            if midi_note is None:
                continue

            # Check if drum is muted before triggering
            if self.sequencer.is_drum_muted(midi_note):
                continue

            # Apply humanization if enabled
            if should_humanize:
                velocity = self.humanizer.humanize_velocity(humanize_amount, velocity)

            # Trigger drum using DrumVoiceManager (handles monophonic synthesis)
            # DrumVoiceManager automatically applies drum-specific parameters
            self.drum_voice_manager.trigger_drum(drum_idx, velocity, humanize_velocity=1.0 if not should_humanize else (velocity / 100.0))

    def _on_sequencer_step(self, step: int):
        """Callback when sequencer advances to a new step."""
        if self.control_panel:
            self.control_panel.update_step(step)
        self._update_playhead(step)

    def _update_playhead(self, step: int):
        """Move the playhead column highlight to the given step."""
        # Clear the previous playhead column
        if self.playhead_step >= 0:
            for row in self.drum_rows:
                if self.playhead_step < len(row.cells):
                    row.cells[self.playhead_step].remove_class("playing")

        # Set new playhead column
        self.playhead_step = step
        for row in self.drum_rows:
            if step < len(row.cells):
                row.cells[step].add_class("playing")

    def _clear_playhead(self):
        """Remove playhead highlight from all cells."""
        if self.playhead_step >= 0:
            for row in self.drum_rows:
                if self.playhead_step < len(row.cells):
                    row.cells[self.playhead_step].remove_class("playing")
        self.playhead_step = -1

    def _save_last_pattern(self, pattern_num: int):
        """Save the last edited pattern number for the next session."""
        import json
        from pathlib import Path

        try:
            state_file = Path("patterns") / ".last_pattern"
            state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(state_file, "w") as f:
                json.dump({"last_pattern": pattern_num}, f)
        except Exception:
            pass  # Silently ignore save errors

    def _load_last_pattern(self) -> int:
        """Load the last edited pattern number from the previous session."""
        import json
        from pathlib import Path

        try:
            state_file = Path("patterns") / ".last_pattern"
            if state_file.exists():
                with open(state_file, "r") as f:
                    data = json.load(f)
                    pattern_num = data.get("last_pattern", 1)
                    return pattern_num
        except Exception:
            pass  # Silently ignore load errors

        return 1  # Default to pattern 1
