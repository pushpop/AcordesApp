"""Real-time piano display and chord detection screen."""
from textual.widget import Widget
from textual.containers import Vertical, Center
from textual.widgets import Label
from textual.message import Message
from typing import TYPE_CHECKING, Set

from components.piano_widget import PianoWidget
from components.chord_display import ChordDisplay
from components.staff_widget import StaffWidget
from components.header_widget import HeaderWidget

if TYPE_CHECKING:
    from midi.input_handler import MIDIInputHandler
    from music.chord_detector import ChordDetector
    from music.synth_engine import SynthEngine


class NoteEvent(Message):
    """Message sent when MIDI notes change."""

    def __init__(self, notes: Set[int]):
        super().__init__()
        self.notes = notes


class PianoMode(Widget):
    """Widget for real-time piano display and chord detection."""

    CSS = """
    PianoMode {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    #piano-section {
        layout: vertical;
        width: 100%;
        height: 43%;
        text-align: center;
        content-align: center middle;
        background: #1a1a1a;
        padding: 1;
    }

    #staff-section {
        width: 100%;
        height: 48%;
        align: center top;
        background: #0a0a0a;
        padding: 0;
    }

    #piano {
        width: 100%;
        height: auto;
        text-align: center;
        content-align: center middle;
        color: #ffffff;
        background: #1a1a1a;
    }

    #status {
        width: 100%;
        height: auto;
        content-align: center middle;
        padding: 1 0;
        color: #666666;
        text-style: italic;
    }

    #staff-display {
        width: auto;
        height: auto;
        content-align: center top;
        text-align: center;
        padding: 0;
        background: #0a0a0a;
    }

    #chord-display {
        width: auto;
        height: auto;
        min-height: 1;
        content-align: center middle;
        text-align: center;
        padding: 0 4;
        margin: 0;
        background: transparent;
    }
    """

    def __init__(self, midi_handler: 'MIDIInputHandler',
                 chord_detector: 'ChordDetector',
                 synth_engine: 'SynthEngine'):
        super().__init__()
        self.midi_handler = midi_handler
        self.chord_detector = chord_detector
        self.synth_engine = synth_engine
        self.piano_widget = None
        self.chord_display_widget = None
        self.staff_widget = None
        # Track last displayed note set — only redraw when it actually changes
        self._last_displayed_notes: Set[int] = set()

    def compose(self):
        """Compose the piano mode layout."""
        # Header section
        self.header = HeaderWidget(
            title=self._get_acordes_ascii(),
            subtitle=self._get_status_text(),
            is_big=True,
            id="title-section"
        )
        yield self.header

        # Chord display section (above piano)
        with Center():
            self.chord_display_widget = ChordDisplay(id="chord-display")
            yield self.chord_display_widget

        # Piano section (middle - 43%)
        with Vertical(id="piano-section"):
            # Piano keyboard
            with Center():
                self.piano_widget = PianoWidget(id="piano")
                yield self.piano_widget

        # Staff section (bottom - 56%)
        with Vertical(id="staff-section"):
            # Musical staff
            with Center():
                self.staff_widget = StaffWidget(id="staff-display")
                yield self.staff_widget

    def on_mount(self):
        """Called when screen is mounted."""
        # Set up MIDI callbacks
        self.midi_handler.set_callbacks(
            note_on=self._on_note_on,
            note_off=self._on_note_off
        )

        # Initialize chord display
        if self.chord_display_widget:
            self.chord_display_widget.update_display(None, [])

        # Initialize staff display
        if self.staff_widget:
            self.staff_widget.update_notes(set())

        # Start polling for MIDI messages
        self.set_interval(0.01, self._poll_midi)  # Poll every 10ms

    def _poll_midi(self):
        """Poll for MIDI messages."""
        if self.midi_handler.is_device_open():
            self.midi_handler.poll_messages()
            # Only redraw when the active note set actually changes
            active_notes = self.midi_handler.get_active_notes()
            if active_notes != self._last_displayed_notes:
                self._last_displayed_notes = active_notes
                self._update_display(active_notes)

    def _on_note_on(self, note: int, velocity: int):
        """Callback for note on events with velocity."""
        # Visual updates happen in _poll_midi
        # Play audio using synth engine
        self.synth_engine.note_on(note, velocity)

    def _on_note_off(self, note: int):
        """Callback for note off events."""
        # Visual updates happen in _poll_midi
        # Stop audio using synth engine
        self.synth_engine.note_off(note)

    def _update_display(self, notes: Set[int]):
        """Update the piano and chord display."""
        # Update piano widget
        if self.piano_widget:
            self.piano_widget.update_notes(notes)

        # Detect and display chord
        if self.chord_display_widget:
            chord_name = self.chord_detector.detect_chord(notes)
            note_names = self.chord_detector.get_note_names(notes)
            self.chord_display_widget.update_display(chord_name, note_names)

        # Update musical staff
        if self.staff_widget:
            self.staff_widget.update_notes(notes)

    def _get_status_text(self) -> str:
        """Get status text based on MIDI connection."""
        if self.midi_handler.is_device_open():
            return "🎵 MIDI device connected - Play some notes!"
        else:
            return "⚠ No MIDI device connected - Select one in Config Mode"

    def _get_acordes_ascii(self) -> str:
        """Get the ACORDES ASCII art."""
        return """
   █████╗  ██████╗ ██████╗ ██████╗ ██████╗ ███████╗███████╗
  ██╔══██╗██╔════╝██╔═══██╗██╔══██╗██╔══██╗██╔════╝██╔════╝
  ███████║██║     ██║   ██║██████╔╝██║  ██║█████╗  ███████╗
  ██╔══██║██║     ██║   ██║██╔══██╗██║  ██║██╔══╝  ╚════██║
  ██║  ██║╚██████╗╚██████╔╝██║  ██║██████╔╝███████╗███████║
  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝
"""
