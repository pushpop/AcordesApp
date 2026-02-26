"""ABOUTME: Reusable header widget for consistent visual style across modes.
ABOUTME: Creates centered, boxed titles with optional ASCII art display."""

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

    .header-blocks {
        width: auto;
        height: auto;
        text-align: center;
        margin-bottom: 0;
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

        # Show TR-inspired colored blocks instead of subtitle
        with Center():
            yield Static(self._create_tr_blocks(), classes="header-blocks")

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

    def _create_tr_blocks(self) -> str:
        """Create drum machine inspired colored blocks (8 blocks with 4 color pairs)."""
        # Use block characters with color coding:
        # Red pair (██), Orange pair (▓▓), Yellow pair (▒▒), White pair (░░)
        red_pair = "[#ff3333]██[/]"  # Red
        orange_pair = "[#ff9933]▓▓[/]"  # Orange
        yellow_pair = "[#ffdd00]▒▒[/]"  # Yellow
        white_pair = "[#ffffff]░░[/]"  # White

        return f"{red_pair}{orange_pair}{yellow_pair}{white_pair}"

    def update_subtitle(self, new_subtitle: str):
        """Update the subtitle/status text."""
        try:
            status_label = self.query_one("#header-status", Static)
            status_label.update(f"[italic #666666]{new_subtitle}[/]")
        except:
            pass
