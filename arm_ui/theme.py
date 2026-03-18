# ABOUTME: Visual theme constants for the ARM Pygame UI (480x320 framebuffer).
# ABOUTME: All colors, font sizes, and layout values are defined here - nowhere else.

import pygame

# Screen dimensions (matches TFT-LCD and HDMI output configured in tft_config.txt)
SCREEN_W = 480
SCREEN_H = 320

# ── Colors ──────────────────────────────────────────────────────────────────
# Elektron/OP-1 inspired: pure black bg, white body text, green+orange accents only.
BG_COLOR        = (  0,   0,   0)   # Pure black background
BG_DARK         = (  0,   0,   0)   # Same black for inner panels
BG_PANEL        = (  8,   8,   8)   # Very slightly lighter panel (barely visible)
ACCENT          = (  0, 210,  70)   # Green (active, enabled, playing)
ACCENT_DIM      = (  0,  70,  25)   # Dim green for borders and inactive
HIGHLIGHT       = (255, 140,   0)   # Orange (selected, focused)
HIGHLIGHT_DIM   = ( 90,  50,   0)   # Dim orange for inactive selected borders
TEXT_PRIMARY    = (255, 255, 255)   # Pure white - all body text
TEXT_SECONDARY  = (160, 160, 160)   # Mid grey for secondary info
TEXT_DIM        = ( 70,  70,  70)   # Dark grey for hints and disabled
SUCCESS         = (  0, 255,  80)   # Ready / OK - bright green
ERROR_COLOR     = (255,  60,  60)   # Error / warning
BAR_BG          = ( 18,  18,  18)   # Parameter bar background track
BAR_FG          = ACCENT            # Parameter bar fill (green)
BADGE_BUILTIN   = (  0,  55,  20)   # "Built-in" badge background
BADGE_USER      = ( 70,  45,   0)   # "User" badge background
SEPARATOR       = ( 40,  40,  40)   # Horizontal rule lines

# Minimum touch target size in pixels (both axes)
MIN_TOUCH = 60

# ── Font sizes ───────────────────────────────────────────────────────────────
# Pixel art aesthetic: use exact sizes for crisp bitmap rendering.
FONT_GIANT  = 56   # BPM display, large numeric readouts
FONT_LARGE  = 28   # Preset name, chord name
FONT_MEDIUM = 18   # Button labels, section headers
FONT_SMALL  = 13   # Parameter labels, info text
FONT_TINY   =  9   # Status footnotes, counters, hints

# ── Carousel layout ──────────────────────────────────────────────────────────
CAROUSEL_CENTER_W  = 140
CAROUSEL_CENTER_H  = 150
CAROUSEL_SIDE_W    = 90
CAROUSEL_SIDE_H    = 100
CAROUSEL_FAR_W     = 56
CAROUSEL_FAR_H     = 70
CAROUSEL_CENTER_X  = (SCREEN_W - CAROUSEL_CENTER_W) // 2
CAROUSEL_CENTER_Y  = 50
CAROUSEL_ITEM_GAP  = 10   # Pixels between carousel items


def _try_pixel_font(size: int) -> pygame.font.Font:
    """Try to load a pixel-art/monospace font, fall back to pygame built-in.

    Tries Terminus first (installed on OStra), then common monospace fonts.
    All text is rendered with antialias=False for the crisp pixel art look.
    """
    candidates = [
        "terminus",
        "Terminus",
        "terminusfont",
        "dejavusansmono",
        "couriernew",
        "courier",
        "monospace",
    ]
    for name in candidates:
        try:
            font = pygame.font.SysFont(name, size)
            if font:
                return font
        except Exception:
            pass
    return pygame.font.Font(None, size)


# Fonts are populated by arm_ui.app after pygame.init() has been called.
# Access via: theme.FONTS[theme.FONT_MEDIUM]
FONTS: dict = {}


def init_fonts() -> None:
    """Populate FONTS dict. Must be called after pygame.init()."""
    global FONTS
    sizes = [FONT_TINY, FONT_SMALL, FONT_MEDIUM, FONT_LARGE, FONT_GIANT]
    FONTS = {s: _try_pixel_font(s) for s in sizes}


def txt(font_size: int, text: str, color: tuple) -> pygame.Surface:
    """Render text with antialias=False for crisp pixel art look."""
    return FONTS[font_size].render(text, False, color)


def draw_dotted_rect(surface: pygame.Surface, color: tuple,
                     rect, step: int = 3) -> None:
    """Draw a dotted/dashed border around rect - Elektron Digitakt panel style.

    Dots are spaced every `step` pixels on each edge.
    rect can be a pygame.Rect or a (x, y, w, h) tuple.
    """
    if isinstance(rect, (tuple, list)):
        x, y, w, h = rect
    else:
        x, y, w, h = rect.x, rect.y, rect.width, rect.height

    # Top and bottom edges
    for px in range(x, x + w, step):
        surface.set_at((px, y),         color)
        surface.set_at((px, y + h - 1), color)

    # Left and right edges
    for py in range(y, y + h, step):
        surface.set_at((x,         py), color)
        surface.set_at((x + w - 1, py), color)


def draw_corner_marks(surface: pygame.Surface, color: tuple,
                      rect, size: int = 4) -> None:
    """Draw small L-shaped corner marks on all four corners of rect.

    Used instead of a full border for a lighter Elektron-style panel indicator.
    rect can be a pygame.Rect or (x, y, w, h) tuple.
    """
    if isinstance(rect, (tuple, list)):
        x, y, w, h = rect
    else:
        x, y, w, h = rect.x, rect.y, rect.width, rect.height

    r = x + w - 1
    b = y + h - 1
    s = size - 1

    # Top-left
    pygame.draw.line(surface, color, (x,     y), (x + s, y))
    pygame.draw.line(surface, color, (x,     y), (x,     y + s))
    # Top-right
    pygame.draw.line(surface, color, (r - s, y), (r,     y))
    pygame.draw.line(surface, color, (r,     y), (r,     y + s))
    # Bottom-left
    pygame.draw.line(surface, color, (x,     b), (x + s, b))
    pygame.draw.line(surface, color, (x,     b - s), (x, b))
    # Bottom-right
    pygame.draw.line(surface, color, (r - s, b), (r,     b))
    pygame.draw.line(surface, color, (r,     b - s), (r,   b))
