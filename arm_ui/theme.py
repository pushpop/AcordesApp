# ABOUTME: Visual theme constants for the ARM Pygame UI (480x320 framebuffer).
# ABOUTME: All colors, font sizes, and layout values are defined here - nowhere else.

import os
import pygame

# ── Render dimensions ────────────────────────────────────────────────────────
# Screens render to SCREEN_W x SCREEN_H (240x160). The app scales 2x to
# DISPLAY_W x DISPLAY_H (480x320) using nearest-neighbor before writing to fb0.
SCREEN_W     = 240
SCREEN_H     = 160
DISPLAY_W    = 480
DISPLAY_H    = 320
RENDER_SCALE = 2

# ── Colors ──────────────────────────────────────────────────────────────────
# Elektron/OP-1 inspired: black bg, white body text, green accent only.
BG_COLOR        = (  0,   0,   0)   # Pure black background
BG_DARK         = (  0,   0,   0)   # Same black for inner panels
BG_PANEL        = (  8,   8,   8)   # Very slightly lighter panel
ACCENT          = (  0, 210,  70)   # Green (active, enabled, playing)
ACCENT_DIM      = (  0,  70,  25)   # Dim green for bar borders
HIGHLIGHT       = (255, 140,   0)   # Orange (status indicators only)
HIGHLIGHT_DIM   = ( 90,  50,   0)   # Dim orange
TEXT_PRIMARY    = (255, 255, 255)   # Pure white - all body text
TEXT_SECONDARY  = (160, 160, 160)   # Mid grey for secondary info
TEXT_DIM        = ( 70,  70,  70)   # Dark grey for hints and disabled
BORDER_ACTIVE   = (255, 255, 255)   # White - selected/active box border
BORDER_INACTIVE = ( 45,  45,  45)   # Dark grey - inactive box border
SUCCESS         = (  0, 255,  80)   # Ready / OK
ERROR_COLOR     = (255,  60,  60)   # Error / warning
BAR_BG          = ( 18,  18,  18)   # Parameter bar background track
BAR_FG          = ACCENT            # Parameter bar fill (green)
SEPARATOR       = ( 35,  35,  35)   # Horizontal rule lines

MIN_TOUCH = 30

# ── Font sizes (at 240x160 internal; appear 2x larger on the 480x320 display) ─
FONT_GIANT  = 32
FONT_LARGE  = 20
FONT_MEDIUM = 14
FONT_SMALL  = 11
FONT_TINY   =  8

# ── Carousel layout ───────────────────────────────────────────────────────────
# All items share the same 3:2 (1.5:1) aspect ratio matching the display.
# Center item: 90x60. Side: 60x40. Far: 36x24.
CAROUSEL_CENTER_W  = 90
CAROUSEL_CENTER_H  = 60
CAROUSEL_SIDE_W    = 60
CAROUSEL_SIDE_H    = 40
CAROUSEL_FAR_W     = 36
CAROUSEL_FAR_H     = 24
CAROUSEL_CENTER_X  = (SCREEN_W - CAROUSEL_CENTER_W) // 2
CAROUSEL_CENTER_Y  = 32
CAROUSEL_ITEM_GAP  = 6


# ── Font loading ──────────────────────────────────────────────────────────────

def _find_bundled_font() -> str | None:
    """Return path to a TTF in arm_ui/fonts/, or None if not found.

    To install Silkscreen (recommended pixel font) on the Pi:
      wget "https://github.com/google/fonts/raw/main/ofl/silkscreen/Silkscreen-Regular.ttf" \\
           -O arm_ui/fonts/Silkscreen.ttf
    Any .ttf file placed in arm_ui/fonts/ is used automatically.
    """
    fonts_dir = os.path.join(os.path.dirname(__file__), "fonts")
    if os.path.isdir(fonts_dir):
        for fname in sorted(os.listdir(fonts_dir)):
            if fname.lower().endswith(".ttf"):
                return os.path.join(fonts_dir, fname)
    return None


def _try_pixel_font(size: int) -> pygame.font.Font:
    """Load a pixel-art font at the given size.

    Priority:
    1. Bundled TTF in arm_ui/fonts/ (place Silkscreen.ttf there)
    2. System monospace fonts (Terminus on OStra, Courier on desktop)
    3. pygame built-in font as last resort
    """
    bundled = _find_bundled_font()
    if bundled:
        try:
            return pygame.font.Font(bundled, size)
        except Exception:
            pass

    for name in ("terminus", "Terminus", "terminusfont",
                 "dejavusansmono", "couriernew", "courier", "monospace"):
        try:
            font = pygame.font.SysFont(name, size)
            if font:
                return font
        except Exception:
            pass

    return pygame.font.Font(None, size)


FONTS: dict = {}


def init_fonts() -> None:
    """Populate FONTS dict. Must be called after pygame.init()."""
    global FONTS
    sizes = [FONT_TINY, FONT_SMALL, FONT_MEDIUM, FONT_LARGE, FONT_GIANT]
    FONTS = {s: _try_pixel_font(s) for s in sizes}


def txt(font_size: int, text: str, color: tuple) -> pygame.Surface:
    """Render text with antialias=False for crisp pixel art look."""
    return FONTS[font_size].render(text, False, color)


def draw_box(surface: pygame.Surface, rect, active: bool = False) -> None:
    """Draw a solid-border box. White border when active, dark grey when inactive.

    All UI panels use this single border style for visual consistency.
    rect can be a pygame.Rect or (x, y, w, h) tuple.
    """
    color = BORDER_ACTIVE if active else BORDER_INACTIVE
    pygame.draw.rect(surface, BG_PANEL, rect)
    pygame.draw.rect(surface, color, rect, 1)


def draw_dotted_rect(surface: pygame.Surface, color: tuple,
                     rect, step: int = 3) -> None:
    """Draw a dotted border - used for parameter bar tracks."""
    if isinstance(rect, (tuple, list)):
        x, y, w, h = rect
    else:
        x, y, w, h = rect.x, rect.y, rect.width, rect.height

    for px in range(x, x + w, step):
        surface.set_at((px, y),         color)
        surface.set_at((px, y + h - 1), color)
    for py in range(y, y + h, step):
        surface.set_at((x,         py), color)
        surface.set_at((x + w - 1, py), color)
