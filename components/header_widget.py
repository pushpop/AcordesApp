"""Reusable header widget for consistent visual style across modes."""
from textual.widgets import Static
from textual.containers import Center, Vertical
from textual.app import ComposeResult

class HeaderWidget(Vertical):
    """A widget that displays a consistent header with optional big ASCII art."""

    DEFAULT_CSS = """
    HeaderWidget {
        width: 100%;
        height: auto;
        align: center top;
        margin-bottom: 1;
    }

    .header-big-ascii {
        width: auto;
        height: auto;
        text-align: center;
        color: #ffd700;
        margin-bottom: 0;
    }

    .header-boxed {
        width: auto;
        height: auto;
        text-align: center;
        color: $accent;
        margin-bottom: 0;
    }

    #header-status {
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def __init__(self, title: str, subtitle: str = "", is_big: bool = False, color: str = "#ffd700", **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.subtitle_text = subtitle
        self.is_big = is_big
        self.color = color

    def compose(self) -> ComposeResult:
        with Center():
            if self.is_big:
                yield Static(self.title_text, classes="header-big-ascii")
            else:
                yield Static(self._create_boxed_title(self.title_text), classes="header-boxed")
        
        if self.subtitle_text:
            with Center():
                yield Static(f"[italic #666666]{self.subtitle_text}[/]", id="header-status")

    def _create_boxed_title(self, title: str, width: int = 48) -> str:
        """Create a boxed title ASCII art."""
        # Pad title with spaces
        title_padded = f" {title} "
        # Use box drawing characters
        inner_width = width - 2
        padding = inner_width - len(title_padded)
        left_pad = padding // 2
        right_pad = padding - left_pad
        
        top = f"╔{'═' * inner_width}╗"
        mid = f"║{' ' * left_pad}{title_padded}{' ' * right_pad}║"
        bottom = f"╚{'═' * inner_width}╝"
        
        return f"{top}\n{mid}\n{bottom}"

    def update_subtitle(self, new_subtitle: str):
        """Update the subtitle/status text."""
        try:
            status_label = self.query_one("#header-status", Static)
            status_label.update(f"[italic #666666]{new_subtitle}[/]")
        except:
            pass
