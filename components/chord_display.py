"""Chord name display widget."""
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text
from rich.console import RenderableType
from rich.align import Align
from rich.panel import Panel
from typing import Optional, List


class ChordDisplay(Widget):
    """Displays detected chord name or note information."""

    chord_name: reactive[Optional[str]] = reactive(None, init=False)
    note_names: reactive[List[str]] = reactive(list, init=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.chord_name = None
        self.note_names = []

    def render(self) -> RenderableType:
        """Render the chord display."""
        if not self.note_names:
            text = Text("♪ No notes playing", style="dim italic #666666", justify="center")
            return Align.center(text)
        elif len(self.note_names) == 1:
            # Make single note larger with spacing
            display_text = f"━━━  {self.note_names[0]}  ━━━"
            text = Text(display_text, style="#00d7ff", justify="center")
        elif self.chord_name:
            # Make chord name much larger and bold with decorative spacing
            display_text = f"━━━  {self.chord_name}  ━━━"
            text = Text(display_text, style="#00ff87", justify="center")
        else:
            notes_str = " ".join(self.note_names)
            display_text = f"━━━  {notes_str}  ━━━"
            text = Text(display_text, style="#ffd700", justify="center")

        # Add padding lines above and below
        result = Text("\n", justify="center")
        result.append(text)
        result.append("\n")

        return Align.center(result)

    def update_display(self, chord_name: Optional[str], note_names: List[str]):
        """Update the chord display.

        Args:
            chord_name: Detected chord name or None.
            note_names: List of note names currently pressed.
        """
        self.chord_name = chord_name
        self.note_names = note_names
        self.refresh()
