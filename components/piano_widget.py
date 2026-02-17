"""Visual piano keyboard widget."""
from textual.widgets import Static
from textual.reactive import reactive
from typing import Set


class PianoWidget(Static):
    """Displays a multi-octave piano keyboard with highlighted keys."""

    # Note names for each semitone
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    active_notes: reactive[Set[int]] = reactive(set, init=False)

    DEFAULT_CSS = """
    PianoWidget {
        height: auto;
        min-height: 11;
        width: 100%;
        content-align: center middle;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.active_notes = set()

    def _build_piano_display(self, active_notes: Set[int]) -> str:
        """Build piano keyboard ASCII art with taller keys and coloring."""
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
                # Check for existing styles...
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

    def render(self) -> str:
        """Render the piano widget."""
        return self._build_piano_display(self.active_notes)

    def update_notes(self, notes: Set[int]):
        """Update the set of active notes.

        Args:
            notes: Set of MIDI note numbers to display as pressed.
        """
        self.active_notes = notes
        self.refresh()

