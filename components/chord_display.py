"""Chord name display widget."""
from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text
from rich.console import RenderableType
from rich.align import Align
from rich.panel import Panel
from typing import Optional, List


class ChordDisplay(Static):
    """Displays detected chord name or note information."""

    chord_name: reactive[Optional[str]] = reactive(None, init=False)
    note_names: reactive[List[str]] = reactive(list, init=False)

    def __init__(self, **kwargs):
        # Initialize with dash to maintain consistent height
        initial_text = Text("─", style="dim #333333", justify="center")
        super().__init__(initial_text, **kwargs)
        self.chord_name = None
        self.note_names = []

    def update_display(self, chord_name: Optional[str], note_names: List[str]):
        """Update the chord display.

        Args:
            chord_name: Detected chord name or None.
            note_names: List of note names currently pressed.
        """
        self.chord_name = chord_name
        self.note_names = note_names

        # Build the display content - ALWAYS single line with consistent format
        # Use dash placeholder for empty state to maintain visible height
        if not note_names:
            display_text = "─"
            text = Text(display_text, style="dim #333333")
        elif len(note_names) == 1:
            display_text = f"{note_names[0]}"
            text = Text(display_text, style="#00d7ff bold")
        elif chord_name:
            display_text = f"{chord_name}"
            text = Text(display_text, style="#00ff87 bold")
        else:
            notes_str = " ".join(note_names)
            display_text = f"{notes_str}"
            text = Text(display_text, style="#ffd700 bold")

        # Update the widget content directly with Align.center for proper centering
        self.update(Align.center(text))
