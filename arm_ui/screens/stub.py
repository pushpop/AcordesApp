# ABOUTME: Stub placeholder screen used for modes not yet implemented in the ARM UI.
# ABOUTME: Displays the mode name and a "coming soon" message; B/Esc returns to main menu.

import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui import theme
from gamepad.actions import GP


class StubScreen(BaseScreen):
    """Placeholder shown for modes not yet fully implemented. Coords: 240x160."""

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

        # Consistent panel: white border box (active style)
        box_w, box_h = 130, 50
        box_x = cx - box_w // 2
        box_y = cy - box_h // 2

        theme.draw_box(surface, (box_x, box_y, box_w, box_h), active=True)

        # Screen label in green at top of panel
        lbl = theme.txt(theme.FONT_TINY, self._title.upper(), theme.ACCENT)
        surface.blit(lbl, lbl.get_rect(centerx=cx, y=box_y + 5))

        pygame.draw.line(surface, theme.SEPARATOR,
                         (box_x + 4, box_y + 14), (box_x + box_w - 4, box_y + 14))

        soon = theme.txt(theme.FONT_SMALL, "COMING SOON", theme.TEXT_PRIMARY)
        surface.blit(soon, soon.get_rect(centerx=cx, y=box_y + 18))

        back = theme.txt(theme.FONT_TINY, "Esc: back", theme.TEXT_DIM)
        surface.blit(back, back.get_rect(centerx=cx, y=theme.SCREEN_H - 9))
