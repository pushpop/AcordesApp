"""Visual piano keyboard widget."""
from textual.widgets import Static
from textual.reactive import reactive
from typing import Set


class PianoWidget(Static):
    """Displays a multi-octave piano keyboard with highlighted keys."""

    # Default: 3 octaves starting from C3 (MIDI note 48)
    START_NOTE = 48  # C3
    NUM_OCTAVES = 3
    NOTES_PER_OCTAVE = 12

    # Note names for each semitone
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    # Which notes are black keys (1-indexed position in octave)
    BLACK_KEYS = {1, 3, 6, 8, 10}  # C#, D#, F#, G#, A#

    active_notes: reactive[Set[int]] = reactive(set, init=False)

    DEFAULT_CSS = """
    PianoWidget {
        height: auto;
        min-height: 5;
    }
    """

    def __init__(self, **kwargs):
        # Build initial display with no active notes (before super init)
        initial_display = self._build_piano_display_static(set())
        super().__init__(initial_display, **kwargs)
        # Now we can set reactives after super().__init__()
        self.active_notes = set()

    def _build_piano_display_static(self, active_notes: Set[int]) -> str:
        """Build the piano keyboard display with given active notes."""
        lines = []

        # Piano layout: C D E F G A B (7 white keys per octave)
        # Black keys: C# D# (gap) F# G# A# (2 + 3 pattern)
        # Pattern per octave: W B W B W | W B W B W B W
        #                     C C# D D# E | F F# G G# A A# B

        # Build all 5 lines as simple strings
        line1 = ""  # Top of black keys
        line2 = ""  # Black keys with press indicator
        line3 = ""  # White keys with note labels
        line4 = ""  # White keys with press indicator
        line5 = ""  # Bottom border

        for octave in range(self.NUM_OCTAVES):
            octave_start = self.START_NOTE + (octave * self.NOTES_PER_OCTAVE)

            # Get the notes for this octave
            notes_in_octave = []
            for i in range(self.NOTES_PER_OCTAVE):
                note_num = octave_start + i
                is_black = i in self.BLACK_KEYS
                is_pressed = note_num in active_notes
                notes_in_octave.append((self.NOTE_NAMES[i], is_black, is_pressed, note_num))

            # Build the keyboard for this octave
            # C with C# black key
            line1 += " ▓▓"
            line2 += " " + ("▓○" if notes_in_octave[1][2] else "▓▓")  # C#
            line3 += "│C │"
            line4 += "│" + (" ○" if notes_in_octave[0][2] else "  ") + "│"  # C
            line5 += "└──┘"

            # D with D# black key
            line1 += " ▓▓"
            line2 += " " + ("▓○" if notes_in_octave[3][2] else "▓▓")  # D#
            line3 += "D │"
            line4 += (" ○" if notes_in_octave[2][2] else "  ") + "│"  # D
            line5 += "──┘"

            # E (no black key after - gap before F)
            line1 += "   "
            line2 += "   "
            line3 += "E │"
            line4 += (" ○" if notes_in_octave[4][2] else "  ") + "│"  # E
            line5 += "──┘"

            # F with F# black key
            line1 += " ▓▓"
            line2 += " " + ("▓○" if notes_in_octave[6][2] else "▓▓")  # F#
            line3 += "F │"
            line4 += (" ○" if notes_in_octave[5][2] else "  ") + "│"  # F
            line5 += "──┘"

            # G with G# black key
            line1 += " ▓▓"
            line2 += " " + ("▓○" if notes_in_octave[8][2] else "▓▓")  # G#
            line3 += "G │"
            line4 += (" ○" if notes_in_octave[7][2] else "  ") + "│"  # G
            line5 += "──┘"

            # A with A# black key
            line1 += " ▓▓"
            line2 += " " + ("▓○" if notes_in_octave[10][2] else "▓▓")  # A#
            line3 += "A │"
            line4 += (" ○" if notes_in_octave[9][2] else "  ") + "│"  # A
            line5 += "──┘"

            # B (no black key after)
            line1 += "   "
            line2 += "   "
            line3 += "B │"
            line4 += (" ○" if notes_in_octave[11][2] else "  ") + "│"  # B
            line5 += "──┘"

        lines = [line1, line2, line3, line4, line5]
        piano_display = "\n".join(lines)
        return piano_display

    def _build_piano_display(self) -> str:
        """Build the piano keyboard display using current active notes."""
        return self._build_piano_display_static(self.active_notes)

    def on_mount(self) -> None:
        """Ensure piano is rendered when mounted."""
        # Build and display the piano
        display_text = self._build_piano_display()
        # Add a test line to verify rendering
        test_display = "=== PIANO KEYBOARD ===\n" + display_text + "\n=== END PIANO ==="
        self.update(test_display)

    def update_notes(self, notes: Set[int]):
        """Update the set of active notes.

        Args:
            notes: Set of MIDI note numbers to display as pressed.
        """
        self.active_notes = notes
        # Update the Static widget content
        self.update(self._build_piano_display())
