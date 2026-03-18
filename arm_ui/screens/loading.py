# ABOUTME: Loading screen shown while the SynthEngineProxy subprocess starts.
# ABOUTME: Displays animated progress bar and transitions to main_menu when ready.

import math
import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui import theme


class LoadingScreen(BaseScreen):
    """Animated loading screen with pixel art style."""

    _CYCLE_PERIOD    = 3.0   # Seconds for one full 0-99% animation cycle
    _DONE_HOLD       = 1.0   # Seconds to hold at 100% before transitioning
    _TRANSITION_DONE = "main_menu"

    def __init__(self, app) -> None:
        super().__init__(app)
        self._elapsed      = 0.0
        self._done_timer   = 0.0
        self._is_done      = False
        self._transitioned = False

    def on_enter(self, **kwargs) -> None:
        self._elapsed      = 0.0
        self._done_timer   = 0.0
        self._is_done      = False
        self._transitioned = False

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.quit()

    def update(self, dt: float) -> None:
        self._elapsed += dt
        self.app.request_redraw()   # always animating during load

        if self._transitioned:
            return

        engine = self.app.synth_engine
        if engine is not None and engine.is_available():
            self._is_done = True

        if self._is_done:
            self._done_timer += dt
            if self._done_timer >= self._DONE_HOLD:
                self._transitioned = True
                self.app.goto(self._TRANSITION_DONE)

    def _progress(self) -> float:
        if self._is_done:
            return 1.0
        cycle_pos = (self._elapsed % self._CYCLE_PERIOD) / self._CYCLE_PERIOD
        return 0.99 * (0.5 - 0.5 * math.cos(cycle_pos * math.pi))

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(theme.BG_COLOR)

        cx = theme.SCREEN_W // 2
        pct = self._progress()

        # Title - pixel art style with character spacing
        title = theme.txt(theme.FONT_LARGE, "A C O R D E S", theme.ACCENT)
        surface.blit(title, title.get_rect(centerx=cx, y=55))

        # Subtitle / version
        sub = theme.txt(theme.FONT_TINY, "OStra", theme.TEXT_DIM)
        surface.blit(sub, sub.get_rect(centerx=cx, y=95))

        # Status line
        if self._is_done:
            status_text  = "READY"
            status_color = theme.SUCCESS
        else:
            err = self.app.synth_engine.get_error() if self.app.synth_engine else None
            if err:
                status_text  = f"ERR  {err[:30]}"
                status_color = theme.ERROR_COLOR
            else:
                status_text  = "LOADING AUDIO ENGINE"
                status_color = theme.TEXT_SECONDARY

        status = theme.txt(theme.FONT_SMALL, status_text, status_color)
        surface.blit(status, status.get_rect(centerx=cx, y=128))

        # Progress bar - blocky pixel style
        bar_w  = 320
        bar_h  = 8
        bar_x  = (theme.SCREEN_W - bar_w) // 2
        bar_y  = 158
        fill_w = int(bar_w * pct)

        pygame.draw.rect(surface, theme.BAR_BG, (bar_x, bar_y, bar_w, bar_h))
        if fill_w > 0:
            pygame.draw.rect(surface, theme.BAR_FG, (bar_x, bar_y, fill_w, bar_h))
        theme.draw_dotted_rect(surface, theme.ACCENT_DIM, (bar_x, bar_y, bar_w, bar_h), step=4)

        # Percentage
        pct_txt = theme.txt(theme.FONT_TINY, f"{int(pct * 100):3d}%", theme.TEXT_SECONDARY)
        surface.blit(pct_txt, pct_txt.get_rect(centerx=cx, y=bar_y + bar_h + 6))

        # Pixel art spinner - cycling block characters
        _SPIN = ["|", "/", "-", "\\"]
        spin_ch = _SPIN[int(self._elapsed * 6) % len(_SPIN)] if not self._is_done else "*"
        spin = theme.txt(theme.FONT_SMALL, spin_ch, theme.HIGHLIGHT)
        surface.blit(spin, spin.get_rect(x=bar_x - 20, y=bar_y - 2))

        # Bottom hint
        hint = theme.txt(theme.FONT_TINY, "Esc: quit", theme.TEXT_DIM)
        surface.blit(hint, (theme.SCREEN_W - hint.get_width() - 6, theme.SCREEN_H - 16))
