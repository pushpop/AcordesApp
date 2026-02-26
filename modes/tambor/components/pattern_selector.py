"""ABOUTME: Pattern selector widget - allows user to navigate and select from 64 patterns.
ABOUTME: Displays as an overlay dialog with keyboard navigation (arrows, Enter, Esc)."""

from textual.widget import Widget
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Label
from textual.binding import Binding
from textual.screen import Screen
from typing import Callable, Optional


class PatternCell(Static):
    """A single pattern cell in the selector grid."""

    DEFAULT_CSS = """
    PatternCell {
        width: 6;
        height: 2;
        border: solid #666666;
        align: center middle;
        background: transparent;
        color: #CCCCCC;
        padding: 0;
        margin: 0;
    }

    PatternCell.selected {
        background: #0080FF 50%;
        color: #FFFFFF;
        border: inner #FF8800;
    }

    PatternCell.saved {
        color: #FFFFFF;
        background: #006400;
        border: inner #00FF00;
    }

    PatternCell.selected.saved {
        background: transparent;
        color: #006400;
        border: heavy #FF8800;
    }
    """

    def __init__(self, pattern_num: int, is_saved: bool = False):
        """Initialize pattern cell."""
        super().__init__()
        self.pattern_num = pattern_num
        self.is_saved = is_saved
        self.selected = False
        # Apply saved CSS class if pattern is saved
        if is_saved:
            self.add_class("saved")

    def render(self) -> str:
        """Render the pattern number."""
        text = f"{self.pattern_num:02d}"
        return text

    def set_selected(self, selected: bool):
        """Mark this cell as selected."""
        self.selected = selected
        if selected:
            self.add_class("selected")
        else:
            self.remove_class("selected")

    def set_saved(self, saved: bool):
        """Mark this cell as having saved data."""
        self.is_saved = saved
        if saved:
            self.add_class("saved")
        else:
            self.remove_class("saved")


class PatternSelector(Static):
    """
    Pattern selector overlay - shows 64 patterns in an 8x8 grid.
    User navigates with arrow keys, selects with Enter, cancels with Esc.
    """

    DEFAULT_CSS = """
    PatternSelector {
        width: 60;
        height: 24;
        background: $boost;
        border: solid #FFFF00;
        layout: vertical;
        align: center middle;
        offset: 10 5;
    }

    PatternSelector > #header {
        height: 2;
        background: $accent;
        border-bottom: solid #FFFF00;
        color: #FFFFFF;
        align: center middle;
    }

    PatternSelector > #grid-container {
        width: 1fr;
        height: 1fr;
        layout: vertical;
    }

    PatternSelector > #footer {
        height: 1;
        background: $accent;
        border-top: solid #FFFF00;
        color: #CCCCCC;
    }
    """

    BINDINGS = [
        Binding("up", "move_up", show=False),
        Binding("down", "move_down", show=False),
        Binding("left", "move_left", show=False),
        Binding("right", "move_right", show=False),
        Binding("enter", "confirm", show=False),
        Binding("escape", "cancel", show=False),
    ]

    def __init__(
        self,
        current_pattern: int = 1,
        on_select: Optional[Callable[[int], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        saved_patterns: Optional[set] = None,
    ):
        """
        Initialize pattern selector.

        Args:
            current_pattern: Currently active pattern number (will be highlighted)
            on_select: Callback when user selects a pattern
            on_cancel: Callback when user cancels (presses Esc)
            saved_patterns: Set of pattern numbers that have saved files
        """
        super().__init__()
        self.current_pattern = current_pattern
        self.on_select = on_select
        self.on_cancel = on_cancel
        self.saved_patterns = saved_patterns or set()

        # Grid state: 8x8 grid = 64 patterns
        self.grid_cols = 8
        self.grid_rows = 8
        self.selected_row = (current_pattern - 1) // self.grid_cols
        self.selected_col = (current_pattern - 1) % self.grid_cols

        self.cells = []  # Will store all PatternCell widgets

    def compose(self):
        """Compose the selector UI."""
        # Header
        header = Label(f"Pattern Selector (Current: {self.current_pattern:02d}/64)", id="header")
        yield header

        # Grid container (8 rows, each with 8 cells)
        with Vertical(id="grid-container"):
            for row in range(self.grid_rows):
                with Horizontal():
                    for col in range(self.grid_cols):
                        pattern_num = row * self.grid_cols + col + 1
                        cell = PatternCell(
                            pattern_num=pattern_num,
                            is_saved=pattern_num in self.saved_patterns,
                        )

                        # Highlight current pattern
                        if pattern_num == self.current_pattern:
                            cell.set_selected(True)

                        self.cells.append(cell)
                        yield cell

        # Footer with instructions
        footer = Label("↑↓←→: Navigate | Enter: Select | Esc: Cancel", id="footer")
        yield footer

    def action_move_up(self):
        """Move selection up."""
        if self.selected_row > 0:
            self.selected_row -= 1
            self._update_selection()

    def action_move_down(self):
        """Move selection down."""
        if self.selected_row < self.grid_rows - 1:
            self.selected_row += 1
            self._update_selection()

    def action_move_left(self):
        """Move selection left."""
        if self.selected_col > 0:
            self.selected_col -= 1
            self._update_selection()

    def action_move_right(self):
        """Move selection right."""
        if self.selected_col < self.grid_cols - 1:
            self.selected_col += 1
            self._update_selection()

    def action_confirm(self):
        """Confirm selection and close."""
        selected_pattern = self.selected_row * self.grid_cols + self.selected_col + 1
        if self.on_select:
            self.on_select(selected_pattern)
        self.remove()

    def action_cancel(self):
        """Cancel selection and close."""
        if self.on_cancel:
            self.on_cancel()
        self.remove()

    def _update_selection(self):
        """Update visual selection in grid."""
        for idx, cell in enumerate(self.cells):
            row = idx // self.grid_cols
            col = idx % self.grid_cols
            if row == self.selected_row and col == self.selected_col:
                cell.set_selected(True)
            else:
                cell.set_selected(False)

        # Update header with selected pattern number
        selected_pattern = self.selected_row * self.grid_cols + self.selected_col + 1
        try:
            self.query_one("#header").update(
                f"Pattern Selector (Current: {self.current_pattern:02d}/64 | Select: {selected_pattern:02d})"
            )
        except:
            pass


class PatternSelectorScreen(Screen):
    """Modal screen for pattern selection - proper modal that takes over input."""

    CSS = """
    PatternSelectorScreen {
        layout: vertical;
        align: center middle;
    }

    PatternSelectorScreen > Vertical {
        width: 52;
        height: auto;
        padding: 0;
        margin: 0;
        align: center middle;
    }

    #grid-container {
        height: 18;
        width: 52;
        border: solid #FFFF00;
        padding: 0;
        margin: 0;
    }

    PatternSelectorScreen > Vertical > Vertical {
        height: auto;
        width: 52;
        padding: 0;
        margin: 0;
    }

    PatternSelectorScreen > Vertical > Horizontal {
        height: 2;
        width: 52;
        padding: 0;
        margin: 0;
    }
    """

    BINDINGS = [
        Binding("up", "move_up", show=False),
        Binding("down", "move_down", show=False),
        Binding("left", "move_left", show=False),
        Binding("right", "move_right", show=False),
        Binding("enter", "confirm", show=False),
        Binding("escape", "cancel", show=False),
        Binding("n", "cancel", show=False),
        Binding("c", "delete_pattern", show=False),
    ]

    def __init__(
        self,
        current_pattern: int = 1,
        on_select: Optional[Callable[[int], None]] = None,
        on_delete: Optional[Callable[[int], None]] = None,
        saved_patterns: Optional[set] = None,
    ):
        """Initialize pattern selector screen."""
        super().__init__()
        self.current_pattern = current_pattern
        self.on_select = on_select
        self.on_delete = on_delete
        self.saved_patterns = saved_patterns or set()

        # Grid state
        self.grid_cols = 8
        self.grid_rows = 8
        self.selected_row = (current_pattern - 1) // self.grid_cols
        self.selected_col = (current_pattern - 1) % self.grid_cols
        self.cells = []

    def compose(self):
        """Compose the pattern selector UI."""
        # Container for the selector
        with Vertical():
            # Header
            header = Label(
                f"Pattern Selector (Current: {self.current_pattern:02d}/64)",
                id="header"
            )
            yield header

            # Grid container
            with Vertical(id="grid-container"):
                for row in range(self.grid_rows):
                    with Horizontal():
                        for col in range(self.grid_cols):
                            pattern_num = row * self.grid_cols + col + 1
                            cell = PatternCell(
                                pattern_num=pattern_num,
                                is_saved=pattern_num in self.saved_patterns,
                            )
                            if pattern_num == self.current_pattern:
                                cell.set_selected(True)
                            self.cells.append(cell)
                            yield cell

            # Footer
            footer = Label(
                "ESC: Cancel | ENTER: Select",
                id="footer"
            )
            yield footer

    def action_move_up(self):
        """Move selection up."""
        if self.selected_row > 0:
            self.selected_row -= 1
            self._update_selection()

    def action_move_down(self):
        """Move selection down."""
        if self.selected_row < self.grid_rows - 1:
            self.selected_row += 1
            self._update_selection()

    def action_move_left(self):
        """Move selection left."""
        if self.selected_col > 0:
            self.selected_col -= 1
            self._update_selection()

    def action_move_right(self):
        """Move selection right."""
        if self.selected_col < self.grid_cols - 1:
            self.selected_col += 1
            self._update_selection()

    def action_confirm(self):
        """Confirm selection and close."""
        selected_pattern = self.selected_row * self.grid_cols + self.selected_col + 1
        if self.on_select:
            self.on_select(selected_pattern)
        self.app.pop_screen()

    def action_cancel(self):
        """Cancel selection and close."""
        self.app.pop_screen()

    def action_delete_pattern(self):
        """Clear the selected pattern (X key)."""
        selected_pattern = self.selected_row * self.grid_cols + self.selected_col + 1
        # Call callback to clear pattern in TamborMode
        if hasattr(self, 'on_delete'):
            self.on_delete(selected_pattern)

        # Update the cell visual to show as empty (remove .saved class)
        cell_idx = self.selected_row * self.grid_cols + self.selected_col
        if cell_idx < len(self.cells):
            cell = self.cells[cell_idx]
            cell.set_saved(False)  # Remove green color, show as empty outline

    def _update_selection(self):
        """Update visual selection in grid."""
        for idx, cell in enumerate(self.cells):
            row = idx // self.grid_cols
            col = idx % self.grid_cols
            if row == self.selected_row and col == self.selected_col:
                cell.set_selected(True)
            else:
                cell.set_selected(False)

        # Update header
        selected_pattern = self.selected_row * self.grid_cols + self.selected_col + 1
        try:
            self.query_one("#header").update(
                f"Pattern Selector (Current: {self.current_pattern:02d}/64 | Select: {selected_pattern:02d})"
            )
        except:
            pass
