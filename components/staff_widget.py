"""Musical staff widget for displaying notes on a traditional staff."""
from textual.widgets import Static
from typing import Set, List


class StaffWidget(Static):
    """Widget that displays notes on a musical staff (treble and bass clef)."""

    # MIDI note 60 = C4 (middle C)
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    def __init__(self, **kwargs):
        # Initialize with empty staff display
        initial_content = self._build_empty_staff()
        super().__init__(initial_content, **kwargs)
        self.active_notes: Set[int] = set()

    def _build_empty_staff(self) -> str:
        """Build an empty staff when no notes are playing."""
        treble = [
            "║                              ║   ",
            "║──────────────────────────────║ F5",
            "║                              ║   ",
            "║──────────────────────────────║ D5",
            "║                              ║   ",
            "║──────────────────────────────║ B4",
            "║                              ║   ",
            "║──────────────────────────────║ G4",
            "║                              ║   ",
            "║──────────────────────────────║ E4",
            "║                              ║   ",
        ]

        bass = [
            "║                              ║   ",
            "║──────────────────────────────║ A3",
            "║                              ║   ",
            "║──────────────────────────────║ F3",
            "║                              ║   ",
            "║──────────────────────────────║ D3",
            "║                              ║   ",
            "║──────────────────────────────║ B2",
            "║                              ║   ",
            "║──────────────────────────────║ G2",
            "║                              ║   ",
        ]

        result = []
        result.append("[bold cyan]Bass Clef (F)[/bold cyan]                              [bold cyan]Treble Clef (G)[/bold cyan]")

        for i in range(len(bass)):
            result.append(f"{bass[i]}        {treble[i]}")

        return "\n".join(result)

    def update_notes(self, notes: Set[int]):
        """Update the staff with new notes.

        Args:
            notes: Set of MIDI note numbers to display.
        """
        self.active_notes = notes
        staff_display = self._build_staff(notes)
        self.update(staff_display)

    def _midi_to_staff_position(self, midi_note: int, is_treble: bool = True) -> int:
        """Convert MIDI note to staff line position.

        For treble clef (G clef):
        - Line 5 (top): F5 (MIDI 77)
        - Line 4: D5 (MIDI 74)
        - Line 3: B4 (MIDI 71)
        - Line 2: G4 (MIDI 67)
        - Line 1 (bottom): E4 (MIDI 64)
        - Middle C (C4, MIDI 60) is below the staff

        For bass clef (F clef):
        - Line 5 (top): A3 (MIDI 57)
        - Line 4: F3 (MIDI 53)
        - Line 3: D3 (MIDI 50)
        - Line 2: B2 (MIDI 47)
        - Line 1 (bottom): G2 (MIDI 43)

        Returns:
            Position relative to staff (negative = below, 0-4 = on lines, 5+ = above)
        """
        if is_treble:
            # E4 (MIDI 64) is line 1 (index 0)
            # Each semitone is 0.5 position
            return (midi_note - 64) // 2
        else:
            # G2 (MIDI 43) is line 1 (index 0)
            return (midi_note - 43) // 2

    def _is_sharp(self, midi_note: int) -> bool:
        """Check if a MIDI note is a sharp/flat (black key)."""
        note_index = midi_note % 12
        return note_index in [1, 3, 6, 8, 10]  # C#, D#, F#, G#, A#

    def _get_note_name_for_display(self, midi_note: int) -> str:
        """Get note name without octave for display."""
        note_index = midi_note % 12
        note_name = self.NOTE_NAMES[note_index]
        # Use flat instead of sharp for better readability in some cases
        flat_names = {
            'C#': 'D♭', 'D#': 'E♭', 'F#': 'G♭',
            'G#': 'A♭', 'A#': 'B♭'
        }
        return flat_names.get(note_name, note_name)

    def _build_staff(self, notes: Set[int]) -> str:
        """Build the musical staff display.

        Args:
            notes: Set of MIDI note numbers to display.

        Returns:
            String representation of the staff with notes.
        """
        if not notes:
            return self._build_empty_staff()

        # Separate notes into treble (>= B3/MIDI 59) and bass (< B3)
        treble_notes = {n for n in notes if n >= 59}
        bass_notes = {n for n in notes if n < 59}

        # Build both staffs
        treble_staff = self._build_clef_staff(treble_notes, is_treble=True)
        bass_staff = self._build_clef_staff(bass_notes, is_treble=False)

        # Split into lines
        treble_lines = treble_staff.split('\n')
        bass_lines = bass_staff.split('\n')

        # Combine side by side
        result = []
        result.append("[bold cyan]Bass Clef (F)[/bold cyan]                              [bold cyan]Treble Clef (G)[/bold cyan]")

        max_lines = max(len(treble_lines), len(bass_lines))
        for i in range(max_lines):
            treble_line = treble_lines[i] if i < len(treble_lines) else " " * 36
            bass_line = bass_lines[i] if i < len(bass_lines) else " " * 36
            result.append(f"{bass_line}        {treble_line}")

        return "\n".join(result)

    def _build_clef_staff(self, notes: Set[int], is_treble: bool = True) -> str:
        """Build a single clef staff (treble or bass).

        Args:
            notes: Set of MIDI notes for this clef.
            is_treble: True for treble clef, False for bass clef.

        Returns:
            String representation of the clef staff.
        """
        # Staff structure: 11 lines total (5 staff lines + 6 spaces between/around)
        # Index 0: Above staff (space)
        # Index 1: Line 5 (top line)
        # Index 2: Space between lines 4-5
        # Index 3: Line 4
        # Index 4: Space between lines 3-4
        # Index 5: Line 3 (middle line)
        # Index 6: Space between lines 2-3
        # Index 7: Line 2
        # Index 8: Space between lines 1-2
        # Index 9: Line 1 (bottom line)
        # Index 10: Below staff (space)

        staff_width = 30

        # Create empty staff lines
        staff_lines = []
        for i in range(11):
            if i in [1, 3, 5, 7, 9]:  # Staff lines
                staff_lines.append("─" * staff_width)
            else:  # Spaces
                staff_lines.append(" " * staff_width)

        # Reference MIDI notes for each line position
        if is_treble:
            # Treble clef: E4 to F5 (MIDI 64 to 77)
            line_notes = {
                9: 64,  # E4
                7: 67,  # G4
                5: 71,  # B4
                3: 74,  # D5
                1: 77,  # F5
            }
            space_notes = {
                10: 62,  # D4 (below staff)
                8: 65,   # F4
                6: 69,   # A4
                4: 72,   # C5
                2: 76,   # E5
                0: 79,   # G5 (above staff)
            }
        else:
            # Bass clef: G2 to A3 (MIDI 43 to 57)
            line_notes = {
                9: 43,  # G2
                7: 47,  # B2
                5: 50,  # D3
                3: 53,  # F3
                1: 57,  # A3
            }
            space_notes = {
                10: 41,  # F2 (below staff)
                8: 45,   # A2
                6: 48,   # C3
                4: 52,   # E3
                2: 55,   # G3
                0: 59,   # B3 (above staff)
            }

        # Track note positions to place them all at once
        note_positions = []  # List of (y_pos, x_pos, is_sharp)

        if notes:
            sorted_notes = sorted(notes)
            # Calculate spacing - leave more room for sharp symbols
            num_notes = len(sorted_notes)
            # Use 80% of staff width for note distribution, centered
            usable_width = int(staff_width * 0.8)
            margin = (staff_width - usable_width) // 2
            note_spacing = usable_width // (num_notes + 1) if num_notes > 0 else usable_width

            for idx, note in enumerate(sorted_notes):
                x_pos = margin + (idx + 1) * note_spacing
                # Ensure we don't go out of bounds
                if x_pos >= staff_width - 2:
                    x_pos = staff_width - 3
                if x_pos < 2:
                    x_pos = 2

                # Find closest staff position
                y_pos = self._find_staff_position(note, line_notes, space_notes)

                # Clamp y_pos to valid range
                if y_pos < 0:
                    y_pos = 0
                elif y_pos > 10:
                    y_pos = 10

                is_sharp = self._is_sharp(note)
                note_positions.append((y_pos, x_pos, is_sharp))

        # Place all notes on the staff lines
        for y_pos, x_pos, is_sharp in note_positions:
            line = staff_lines[y_pos]
            line_chars = list(line)

            # Insert sharp symbol before the note if needed
            if is_sharp and x_pos > 0:
                line_chars[x_pos - 1] = '♯'

            # Place the note
            line_chars[x_pos] = '●'
            staff_lines[y_pos] = ''.join(line_chars)

        # Build final staff with side borders only (no top/bottom)
        result = []

        # Add reference notes on the right
        ref_labels = ["", "F5", "", "D5", "", "B4", "", "G4", "", "E4", ""] if is_treble else ["", "A3", "", "F3", "", "D3", "", "B2", "", "G2", ""]

        for i, line in enumerate(staff_lines):
            label = ref_labels[i] if i < len(ref_labels) else ""

            # Add markup by replacing characters, maintaining exact width
            marked_line = ""
            j = 0
            while j < len(line):
                char = line[j]
                if char == '♯':
                    marked_line += '[yellow]♯[/yellow]'
                elif char == '●':
                    marked_line += '[bold yellow]●[/bold yellow]'
                else:
                    marked_line += char
                j += 1

            # Pad the label to ensure consistent spacing
            label_padded = label.ljust(2)  # Ensure labels are always 2 chars (e.g., "F5")
            result.append(f"║{marked_line}║ {label_padded}")

        return "\n".join(result)

    def _find_staff_position(self, midi_note: int, line_notes: dict, space_notes: dict) -> int:
        """Find the closest staff position for a MIDI note.

        Args:
            midi_note: MIDI note number.
            line_notes: Dict mapping line indices to MIDI notes.
            space_notes: Dict mapping space indices to MIDI notes.

        Returns:
            Staff line index (0-10).
        """
        # Combine all positions
        all_positions = {**line_notes, **space_notes}

        # Find closest position
        closest_pos = min(all_positions.keys(),
                         key=lambda k: abs(all_positions[k] - midi_note))

        # Adjust for notes outside range
        closest_midi = all_positions[closest_pos]
        diff = midi_note - closest_midi

        # Each semitone is approximately 0.5 positions
        # Adjust position based on difference
        adjusted_pos = closest_pos - (diff // 2)

        return max(0, min(10, adjusted_pos))
