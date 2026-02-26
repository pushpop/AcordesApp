"""ABOUTME: Fill pattern selector screen for Tambor drum machine.
ABOUTME: Modal dialog for selecting which fill pattern to assign to current pattern."""

from typing import Optional, Callable
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Button
from textual.binding import Binding
from ..music.fill_presets import get_all_fill_ids, get_fill_names


class FillSelectorScreen(Screen):
    """Modal screen for selecting fill patterns."""

    CSS = """
    FillSelectorScreen {
        align: center middle;
        background: $surface 90%;
    }

    #fill-box {
        width: 90;
        height: auto;
        border: solid #FFA500;
        background: $panel;
    }

    #fill-header {
        width: 100%;
        text-align: center;
        color: $accent;
        background: $boost;
        padding: 1 2;
        border-bottom: solid #FFA500;
        text-style: bold;
    }

    #fill-list {
        width: 100%;
        height: auto;
        padding: 1 2;
    }

    .fill-item {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    .fill-item.selected {
        background: #FFA500 40%;
        color: $text;
    }

    #fill-footer {
        width: 100%;
        text-align: center;
        color: $text-muted;
        padding: 1 2;
        border-top: solid #FFA500;
        background: $boost;
    }
    """

    BINDINGS = [
        Binding("up", "select_previous", "Previous", show=False),
        Binding("down", "select_next", "Next", show=False),
        Binding("enter", "confirm_selection", "Select", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, current_fill_id: Optional[int] = None, on_fill_selected: Optional[Callable] = None):
        """Initialize fill selector.

        Args:
            current_fill_id: Currently assigned fill ID (if any)
            on_fill_selected: Callback function(fill_id) when fill is selected
        """
        super().__init__()
        self.current_fill_id = current_fill_id
        self.on_fill_selected = on_fill_selected
        self.selected_index = 0
        self.fill_ids = get_all_fill_ids()

        # Find current fill in list
        if current_fill_id is not None and current_fill_id in self.fill_ids:
            self.selected_index = self.fill_ids.index(current_fill_id)

        self.fill_names = get_fill_names()

    def compose(self):
        """Compose the fill selector layout."""
        with Vertical(id="fill-box"):
            yield Static("SELECT FILL PATTERN", id="fill-header")

            with Vertical(id="fill-list"):
                # Display all fills
                for i, fill_id in enumerate(self.fill_ids):
                    fill_data = self.fill_names[fill_id]
                    is_selected = i == self.selected_index
                    fill_item = FillItemWidget(
                        fill_id=fill_id,
                        name=fill_data["name"],
                        description=fill_data["description"],
                        is_selected=is_selected,
                        classes="fill-item"
                    )
                    yield fill_item

                # Option for no fill
                is_selected = self.selected_index >= len(self.fill_ids)
                fill_item = FillItemWidget(
                    fill_id=None,
                    name="None",
                    description="No fill pattern",
                    is_selected=is_selected,
                    classes="fill-item"
                )
                yield fill_item

            yield Static("↑↓: Navigate  ENTER: Select  ESC: Cancel", id="fill-footer")

    def action_select_previous(self) -> None:
        """Select previous fill."""
        if self.selected_index > 0:
            self.selected_index -= 1
            self._update_highlights()
            self._scroll_to_selected()

    def action_select_next(self) -> None:
        """Select next fill."""
        # Allow one extra for "None" option
        if self.selected_index < len(self.fill_ids):
            self.selected_index += 1
            self._update_highlights()
            self._scroll_to_selected()

    def action_confirm_selection(self) -> None:
        """Confirm selection and close."""
        # Determine which fill was selected
        if self.selected_index < len(self.fill_ids):
            selected_fill_id = self.fill_ids[self.selected_index]
        else:
            selected_fill_id = None

        # Always call callback first, even if pop_screen fails
        if self.on_fill_selected:
            self.on_fill_selected(selected_fill_id)

        # Close the modal
        try:
            self.app.pop_screen()
        except Exception:
            # If pop fails, that's ok - callback was already called
            pass

    def action_cancel(self) -> None:
        """Cancel selection and close."""
        try:
            self.app.pop_screen()
        except Exception:
            # If pop fails, that's ok
            pass

    def _update_highlights(self) -> None:
        """Update visual highlighting of selected item."""
        # Find all fill item widgets and update their selection state
        fill_items = list(self.query(".fill-item"))
        for i, widget in enumerate(fill_items):
            if i == self.selected_index:
                widget.add_class("selected")
            else:
                widget.remove_class("selected")

    def _scroll_to_selected(self) -> None:
        """Scroll list to ensure selected item is visible."""
        try:
            fill_items = list(self.query(".fill-item"))
            if self.selected_index < len(fill_items):
                selected_widget = fill_items[self.selected_index]
                selected_widget.scroll_visible()
        except Exception:
            pass  # Silently ignore scroll errors


class FillItemWidget(Static):
    """Widget representing a single fill option."""

    def __init__(self, fill_id: Optional[int], name: str, description: str, is_selected: bool = False, **kwargs):
        """Initialize fill item widget.

        Args:
            fill_id: ID of fill (or None for "No fill" option)
            name: Display name of fill
            description: Description text
            is_selected: Whether this item is currently selected
        """
        super().__init__(**kwargs)
        self.fill_id = fill_id
        self.fill_name = name
        self.fill_description = description

        if is_selected:
            self.add_class("selected")

    def render(self) -> str:
        """Render the fill item."""
        if self.fill_id is None:
            return f"[·] {self.fill_name:<25} {self.fill_description}"
        else:
            return f"[{self.fill_id:2d}] {self.fill_name:<25} {self.fill_description}"
