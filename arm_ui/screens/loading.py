# ABOUTME: Loading screen shown while the SynthEngineProxy subprocess starts.
# ABOUTME: Displays animated progress bar and transitions to main_menu when ready.

import math
import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui import theme


class LoadingScreen(BaseScreen):
    """Animated loading screen.

    The progress bar cycles 0-99% to show activity, then snaps to 100% once
    the audio engine reports is_available(). A brief 1.2-second hold at 100%
    gives the user visual confirmation before the main menu appears.
    """

    _CYCLE_PERIOD    = 3.0   # Seconds for one full 0-99% animation cycle
    _DONE_HOLD       = 1.2   # Seconds to hold at 100% before transitioning
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
        self.app.request_redraw()   # loading screen always animates

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
        """Return current progress value in range 0.0-1.0."""
        if self._is_done:
            return 1.0
        # Smooth cycling animation: sin curve mapped to 0.0-0.99
        cycle_pos = (self._elapsed % self._CYCLE_PERIOD) / self._CYCLE_PERIOD
        return 0.99 * (0.5 - 0.5 * math.cos(cycle_pos * math.pi))

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(theme.BG_COLOR)

        font_large  = theme.FONTS[theme.FONT_LARGE]
        font_medium = theme.FONTS[theme.FONT_MEDIUM]
        font_small  = theme.FONTS[theme.FONT_SMALL]

        # App name centered in upper area
        title_surf = font_large.render("A C O R D E S", True, theme.TEXT_PRIMARY)
        title_rect = title_surf.get_rect(centerx=theme.SCREEN_W // 2, y=60)
        surface.blit(title_surf, title_rect)

        # Status line
        if self._is_done:
            status_text = "Ready."
            status_color = theme.SUCCESS
        else:
            err = self.app.synth_engine.get_error() if self.app.synth_engine else None
            if err:
                status_text = f"Error: {err[:38]}"
                status_color = theme.ERROR_COLOR
            else:
                status_text = "Loading audio engine..."
                status_color = theme.TEXT_SECONDARY

        status_surf = font_medium.render(status_text, True, status_color)
        status_rect = status_surf.get_rect(centerx=theme.SCREEN_W // 2, y=130)
        surface.blit(status_surf, status_rect)

        # Progress bar
        bar_w  = 320
        bar_h  = 14
        bar_x  = (theme.SCREEN_W - bar_w) // 2
        bar_y  = 180
        fill_w = int(bar_w * self._progress())

        pygame.draw.rect(surface, theme.BAR_BG,  (bar_x, bar_y, bar_w, bar_h), border_radius=4)
        if fill_w > 0:
            pygame.draw.rect(surface, theme.BAR_FG, (bar_x, bar_y, fill_w, bar_h), border_radius=4)
        pygame.draw.rect(surface, theme.ACCENT_DIM, (bar_x, bar_y, bar_w, bar_h), 1, border_radius=4)

        # Percentage label
        pct_surf = font_small.render(f"{int(self._progress() * 100)}%", True, theme.TEXT_SECONDARY)
        pct_rect = pct_surf.get_rect(centerx=theme.SCREEN_W // 2, y=bar_y + bar_h + 8)
        surface.blit(pct_surf, pct_rect)

        # Version hint at bottom
        ver_surf = font_small.render("OStra", True, theme.TEXT_DIM)
        surface.blit(ver_surf, (theme.SCREEN_W - ver_surf.get_width() - 10, theme.SCREEN_H - 22))
