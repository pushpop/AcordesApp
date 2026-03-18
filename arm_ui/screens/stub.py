# ABOUTME: Stub placeholder screen used for modes not yet implemented in the ARM UI.
# ABOUTME: Displays the mode name and a "coming soon" message; B/Esc returns to main menu.

import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui import theme
from gamepad.actions import GP


class StubScreen(BaseScreen):
    """Placeholder shown for modes not yet fully implemented in the ARM UI."""

    def __init__(self, app, title: str = "Mode") -> None:
        super().__init__(app)
        self._title = title

    def on_enter(self, **kwargs) -> None:
        gp = self.app.gamepad_handler
        gp.set_button_callback(GP.BACK, lambda: self.app.goto("main_menu"))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_b):
                self.app.goto("main_menu")

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(theme.BG_COLOR)
        cx = theme.SCREEN_W // 2
        cy = theme.SCREEN_H // 2

        # Elektron-style panel: dotted border, corner marks
        box_w, box_h = 260, 90
        box_x = cx - box_w // 2
        box_y = cy - box_h // 2
        box_rect = (box_x, box_y, box_w, box_h)

        pygame.draw.rect(surface, theme.BG_PANEL, box_rect)
        theme.draw_dotted_rect(surface, theme.ACCENT_DIM, box_rect, step=4)
        theme.draw_corner_marks(surface, theme.ACCENT, box_rect, size=5)

        # Screen label in green at top of panel
        lbl = theme.txt(theme.FONT_TINY, self._title.upper(), theme.ACCENT)
        surface.blit(lbl, lbl.get_rect(centerx=cx, y=box_y + 8))

        # Separator inside panel
        pygame.draw.line(surface, theme.SEPARATOR,
                         (box_x + 8, box_y + 22), (box_x + box_w - 8, box_y + 22))

        # "Coming soon" in white
        soon = theme.txt(theme.FONT_MEDIUM, "COMING SOON", theme.TEXT_PRIMARY)
        surface.blit(soon, soon.get_rect(centerx=cx, y=box_y + 30))

        # Hint below panel
        back = theme.txt(theme.FONT_TINY, "Esc: back", theme.TEXT_DIM)
        surface.blit(back, back.get_rect(centerx=cx, y=theme.SCREEN_H - 16))
