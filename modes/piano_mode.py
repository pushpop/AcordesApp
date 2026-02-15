"""Real-time piano display and chord detection screen."""
from textual.widget import Widget
from textual.containers import Container, Vertical, Center, Horizontal
from textual.widgets import Static, Label
from textual.binding import Binding
from textual.message import Message
from typing import TYPE_CHECKING, Set

from components.piano_widget import PianoWidget
from components.chord_display import ChordDisplay
from components.staff_widget import StaffWidget

if TYPE_CHECKING:
    from midi.input_handler import MIDIInputHandler
    from music.chord_detector import ChordDetector


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

    #title-section {
        width: 100%;
        height: 8%;
        align: center top;
        background: #0a1f3f;
        padding: 0;
        border-bottom: heavy #ffd700;
    }

    #title {
        width: auto;
        height: auto;
        content-align: center top;
        text-align: center;
        color: #ffd700;
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
                 chord_detector: 'ChordDetector'):
        super().__init__()
        self.midi_handler = midi_handler
        self.chord_detector = chord_detector
        self.piano_widget = None
        self.chord_display_widget = None
        self.staff_widget = None

    def compose(self):
        """Compose the piano mode layout."""
        # Title section (top - 15%)
        with Vertical(id="title-section"):
            with Center():
                yield Label(self._get_acordes_ascii(), id="title")
            # Status
            with Center():
                yield Label(self._get_status_text(), id="status")

        # Chord display section (above piano)
        with Center():
            self.chord_display_widget = ChordDisplay(id="chord-display")
            yield self.chord_display_widget

        # Piano section (middle - 43%)
        with Vertical(id="piano-section"):
            # Piano keyboard
            with Center():
                self.piano_widget = Label(self._build_piano_display(set()), id="piano")
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

        # Initialize piano display
        if self.piano_widget:
            piano_text = self._build_piano_display(set())
            self.piano_widget.update(piano_text)

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
            # Update display with current notes
            active_notes = self.midi_handler.get_active_notes()
            self._update_display(active_notes)

    def _on_note_on(self, note: int, velocity: int):
        """Callback for note on events with velocity."""
        # Updates happen in _poll_midi
        # Velocity is ignored in piano mode (visual only)
        pass

    def _on_note_off(self, note: int):
        """Callback for note off events."""
        # Updates happen in _poll_midi
        pass

    def _build_piano_display(self, active_notes: Set[int]) -> str:
        """Build piano keyboard ASCII art with taller keys and red dots."""
        # Constants
        NOTES_PER_OCTAVE = 12

        # Dynamically determine the range of octaves to display
        if active_notes:
            min_note = min(active_notes)
            max_note = max(active_notes)
            # Calculate octave range
            min_octave = (min_note // 12) - 1
            max_octave = (max_note // 12) - 1
            # Ensure at least 3 octaves displayed
            octave_range = max_octave - min_octave + 1
            if octave_range < 3:
                # Center around the played notes
                min_octave = max(0, min_octave - (3 - octave_range) // 2)
                max_octave = min_octave + 2
            START_NOTE = (min_octave + 1) * 12
            NUM_OCTAVES = max_octave - min_octave + 1
        else:
            # Default: 3 octaves starting from C3
            START_NOTE = 48  # C3
            NUM_OCTAVES = 3

        # Build 11 lines for taller keys (4 for black, 7 for white)
        lines = ["" for _ in range(11)]

        for octave in range(NUM_OCTAVES):
            octave_start = START_NOTE + (octave * NOTES_PER_OCTAVE)
            notes = []
            for i in range(NOTES_PER_OCTAVE):
                note_num = octave_start + i
                is_pressed = note_num in active_notes
                notes.append(is_pressed)

            # C with C# black key
            if notes[1]:  # C# pressed
                lines[0] += " [red on red]▓▓▓[/red on red]"
                lines[1] += " [red on red]▓▓▓[/red on red]"
                lines[2] += " [white on red]C#[/white on red]│"
                lines[3] += " [red on red]▓▓▓[/red on red]"
            else:
                lines[0] += " ▓▓▓"
                lines[1] += " ▓▓▓"
                lines[2] += " C#▓"
                lines[3] += " ▓▓▓"

            if notes[0]:  # C pressed
                lines[4] += "[black on red]│   │[/black on red]"
                lines[5] += "[black on red]│ C │[/black on red]"
                lines[6] += "[black on red]│   │[/black on red]"
                lines[7] += "[black on red]│   │[/black on red]"
                lines[8] += "[black on red]│   │[/black on red]"
                lines[9] += "[black on red]│   │[/black on red]"
                lines[10] += "[black on red]└───┘[/black on red]"
            else:
                lines[4] += "│   │"
                lines[5] += "│ C │"
                lines[6] += "│   │"
                lines[7] += "│   │"
                lines[8] += "│   │"
                lines[9] += "│   │"
                lines[10] += "└───┘"

            # D with D# black key
            if notes[3]:  # D# pressed
                lines[0] += " [red on red]▓▓▓[/red on red]"
                lines[1] += " [red on red]▓▓▓[/red on red]"
                lines[2] += " [white on red]D#[/white on red]│"
                lines[3] += " [red on red]▓▓▓[/red on red]"
            else:
                lines[0] += " ▓▓▓"
                lines[1] += " ▓▓▓"
                lines[2] += " D#▓"
                lines[3] += " ▓▓▓"

            if notes[2]:  # D pressed
                lines[4] += "[black on red]   │[/black on red]"
                lines[5] += "[black on red] D │[/black on red]"
                lines[6] += "[black on red]   │[/black on red]"
                lines[7] += "[black on red]   │[/black on red]"
                lines[8] += "[black on red]   │[/black on red]"
                lines[9] += "[black on red]   │[/black on red]"
                lines[10] += "[black on red]───┘[/black on red]"
            else:
                lines[4] += "   │"
                lines[5] += " D │"
                lines[6] += "   │"
                lines[7] += "   │"
                lines[8] += "   │"
                lines[9] += "   │"
                lines[10] += "───┘"

            # E (no black key)
            lines[0] += "    "
            lines[1] += "    "
            lines[2] += "    "
            lines[3] += "    "

            if notes[4]:  # E pressed
                lines[4] += "[black on red]   │[/black on red]"
                lines[5] += "[black on red] E │[/black on red]"
                lines[6] += "[black on red]   │[/black on red]"
                lines[7] += "[black on red]   │[/black on red]"
                lines[8] += "[black on red]   │[/black on red]"
                lines[9] += "[black on red]   │[/black on red]"
                lines[10] += "[black on red]───┘[/black on red]"
            else:
                lines[4] += "   │"
                lines[5] += " E │"
                lines[6] += "   │"
                lines[7] += "   │"
                lines[8] += "   │"
                lines[9] += "   │"
                lines[10] += "───┘"

            # F with F# black key
            if notes[6]:  # F# pressed
                lines[0] += " [red on red]▓▓▓[/red on red]"
                lines[1] += " [red on red]▓▓▓[/red on red]"
                lines[2] += " [white on red]F#[/white on red]│"
                lines[3] += " [red on red]▓▓▓[/red on red]"
            else:
                lines[0] += " ▓▓▓"
                lines[1] += " ▓▓▓"
                lines[2] += " F#▓"
                lines[3] += " ▓▓▓"

            if notes[5]:  # F pressed
                lines[4] += "[black on red]   │[/black on red]"
                lines[5] += "[black on red] F │[/black on red]"
                lines[6] += "[black on red]   │[/black on red]"
                lines[7] += "[black on red]   │[/black on red]"
                lines[8] += "[black on red]   │[/black on red]"
                lines[9] += "[black on red]   │[/black on red]"
                lines[10] += "[black on red]───┘[/black on red]"
            else:
                lines[4] += "   │"
                lines[5] += " F │"
                lines[6] += "   │"
                lines[7] += "   │"
                lines[8] += "   │"
                lines[9] += "   │"
                lines[10] += "───┘"

            # G with G# black key
            if notes[8]:  # G# pressed
                lines[0] += " [red on red]▓▓▓[/red on red]"
                lines[1] += " [red on red]▓▓▓[/red on red]"
                lines[2] += " [white on red]G#[/white on red]│"
                lines[3] += " [red on red]▓▓▓[/red on red]"
            else:
                lines[0] += " ▓▓▓"
                lines[1] += " ▓▓▓"
                lines[2] += " G#▓"
                lines[3] += " ▓▓▓"

            if notes[7]:  # G pressed
                lines[4] += "[black on red]   │[/black on red]"
                lines[5] += "[black on red] G │[/black on red]"
                lines[6] += "[black on red]   │[/black on red]"
                lines[7] += "[black on red]   │[/black on red]"
                lines[8] += "[black on red]   │[/black on red]"
                lines[9] += "[black on red]   │[/black on red]"
                lines[10] += "[black on red]───┘[/black on red]"
            else:
                lines[4] += "   │"
                lines[5] += " G │"
                lines[6] += "   │"
                lines[7] += "   │"
                lines[8] += "   │"
                lines[9] += "   │"
                lines[10] += "───┘"

            # A with A# black key
            if notes[10]:  # A# pressed
                lines[0] += " [red on red]▓▓▓[/red on red]"
                lines[1] += " [red on red]▓▓▓[/red on red]"
                lines[2] += " [white on red]A#[/white on red]│"
                lines[3] += " [red on red]▓▓▓[/red on red]"
            else:
                lines[0] += " ▓▓▓"
                lines[1] += " ▓▓▓"
                lines[2] += " A#▓"
                lines[3] += " ▓▓▓"

            if notes[9]:  # A pressed
                lines[4] += "[black on red]   │[/black on red]"
                lines[5] += "[black on red] A │[/black on red]"
                lines[6] += "[black on red]   │[/black on red]"
                lines[7] += "[black on red]   │[/black on red]"
                lines[8] += "[black on red]   │[/black on red]"
                lines[9] += "[black on red]   │[/black on red]"
                lines[10] += "[black on red]───┘[/black on red]"
            else:
                lines[4] += "   │"
                lines[5] += " A │"
                lines[6] += "   │"
                lines[7] += "   │"
                lines[8] += "   │"
                lines[9] += "   │"
                lines[10] += "───┘"

            # B (no black key)
            lines[0] += "    "
            lines[1] += "    "
            lines[2] += "    "
            lines[3] += "    "

            if notes[11]:  # B pressed
                lines[4] += "[black on red]   │[/black on red]"
                lines[5] += "[black on red] B │[/black on red]"
                lines[6] += "[black on red]   │[/black on red]"
                lines[7] += "[black on red]   │[/black on red]"
                lines[8] += "[black on red]   │[/black on red]"
                lines[9] += "[black on red]   │[/black on red]"
                lines[10] += "[black on red]───┘[/black on red]"
            else:
                lines[4] += "   │"
                lines[5] += " B │"
                lines[6] += "   │"
                lines[7] += "   │"
                lines[8] += "   │"
                lines[9] += "   │"
                lines[10] += "───┘"

        # Calculate keyboard width dynamically by removing markup tags
        import re
        # Remove all rich markup tags to get visual width from all lines
        max_width = 0
        for line in lines:
            clean_line = re.sub(r'\[.*?\]', '', line)
            max_width = max(max_width, len(clean_line))

        visual_width = max_width + 2  # Add 2 for proper alignment and padding

        # Create bounding box
        top_border = "╔" + "═" * visual_width + "╗"
        bottom_border = "╚" + "═" * visual_width + "╝"

        # Add side borders to each line with proper padding
        bordered_lines = [top_border]
        for line in lines:
            # Calculate how much padding is needed for this line
            clean_line = re.sub(r'\[.*?\]', '', line)
            padding_needed = visual_width - len(clean_line)
            bordered_lines.append("║" + line + " " * padding_needed + "║")
        bordered_lines.append(bottom_border)

        return "\n".join(bordered_lines)

    def _update_display(self, notes: Set[int]):
        """Update the piano and chord display."""
        # Update piano widget
        if self.piano_widget:
            piano_text = self._build_piano_display(notes)
            self.piano_widget.update(piano_text)

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

