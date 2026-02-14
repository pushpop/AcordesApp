"""Centered quit confirmation dialog."""
from textual.screen import ModalScreen
from textual.containers import Container, Vertical
from textual.widgets import Static, Label
from textual.binding import Binding


class ConfirmationDialog(ModalScreen[bool]):
    """A centered modal dialog for confirming quit action."""

    BINDINGS = [
        Binding("y", "confirm_yes", "Yes", show=False),
        Binding("Y", "confirm_yes", "Yes", show=False),
        Binding("n", "confirm_no", "No", show=False),
        Binding("N", "confirm_no", "No", show=False),
        Binding("enter", "confirm_yes", "Confirm", show=False),
        Binding("escape", "confirm_no", "Cancel", show=False),
    ]

    CSS = """
    ConfirmationDialog {
        align: center middle;
    }

    #dialog {
        width: 50;
        height: 9;
        border: thick #ffd700;
        background: #1a1a1a;
        padding: 1 2;
    }

    #message {
        width: 100%;
        content-align: center middle;
        color: #ffd700;
    }

    #options {
        width: 100%;
        height: 3;
        content-align: center middle;
        margin-top: 1;
        color: #ffffff;
    }
    """

    def __init__(self, message: str = "Quit application?"):
        super().__init__()
        self.message = message

    def compose(self):
        """Compose the dialog layout."""
        with Vertical(id="dialog"):
            yield Label(self.message, id="message")
            yield Label("[Y]es  [N]o", id="options", markup=False)

    def action_confirm_yes(self):
        """User confirmed."""
        self.dismiss(True)

    def action_confirm_no(self):
        """User cancelled."""
        self.dismiss(False)
