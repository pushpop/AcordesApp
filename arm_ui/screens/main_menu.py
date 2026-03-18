# ABOUTME: Main menu carousel screen for the ARM Pygame UI.
# ABOUTME: Shows 6 mode icons in a scrollable carousel, navigated by D-pad or touch.

import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui import theme
from gamepad.actions import GP

# Mode definitions: (screen_name, display_label, icon_character)
_MODES = [
    ("piano",      "Piano",      "♪"),
    ("synth",      "Synth",      "~"),
    ("metronome",  "Metronome",  "♩"),
    ("tambor",     "Tambor",     "●"),
    ("compendium", "Compendium", "♫"),
    ("config",     "Config",     "⚙"),
]

_QUIT_CONFIRM  = False  # Module-level default; instance state is per-object


class MainMenuScreen(BaseScreen):
    """Horizontal carousel main menu.

    The selected item is centered and drawn larger. Flanking items are smaller
    and partially visible. A smooth lerp animates the scroll position.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self._selected    = 0
        self._scroll_pos  = 0.0   # Float position that lerps toward _selected
        self._quit_armed  = False  # True after first BACK press; second press quits

    def on_enter(self, **kwargs) -> None:
        self._quit_armed = False
        gp = self.app.gamepad_handler
        gp.set_button_callback(GP.DPAD_LEFT,  self._go_left)
        gp.set_button_callback(GP.DPAD_RIGHT, self._go_right)
        gp.set_button_callback(GP.CONFIRM,    self._select)
        gp.set_button_callback(GP.BACK,       self._back_pressed)

    def on_exit(self) -> None:
        self._quit_armed = False

    def _go_left(self) -> None:
        self._selected = max(0, self._selected - 1)
        self._quit_armed = False
        self.app.request_redraw()

    def _go_right(self) -> None:
        self._selected = min(len(_MODES) - 1, self._selected + 1)
        self._quit_armed = False
        self.app.request_redraw()

    def _select(self) -> None:
        screen_name = _MODES[self._selected][0]
        self.app.goto(screen_name)

    def _back_pressed(self) -> None:
        if self._quit_armed:
            self.app.quit()
        else:
            self._quit_armed = True
            self.app.request_redraw()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            self._handle_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self._handle_touch(event.pos)

    def _handle_key(self, key: int) -> None:
        if key in (pygame.K_LEFT,  pygame.K_a):
            self._go_left()
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._go_right()
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._select()
        elif key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self._back_pressed()

    def _handle_touch(self, pos: tuple) -> None:
        """Select the carousel item under the touch point."""
        x, y = pos
        center_x = theme.SCREEN_W // 2
        item_stride = theme.CAROUSEL_CENTER_W + theme.CAROUSEL_ITEM_GAP

        for i, _ in enumerate(_MODES):
            offset = i - self._selected
            item_cx = center_x + int(offset * item_stride)
            item_w  = theme.CAROUSEL_CENTER_W if i == self._selected else theme.CAROUSEL_SIDE_W
            item_h  = theme.CAROUSEL_CENTER_H if i == self._selected else theme.CAROUSEL_SIDE_H
            item_x  = item_cx - item_w // 2
            item_y  = theme.CAROUSEL_CENTER_Y

            rect = pygame.Rect(item_x, item_y, item_w, item_h)
            if rect.collidepoint(x, y):
                if i == self._selected:
                    self._select()
                else:
                    self._selected = i
                return

    def update(self, dt: float) -> None:
        # Snap scroll position to selected index immediately (no animation)
        self._scroll_pos = float(self._selected)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(theme.BG_COLOR)

        font_large  = theme.FONTS[theme.FONT_LARGE]
        font_medium = theme.FONTS[theme.FONT_MEDIUM]
        font_small  = theme.FONTS[theme.FONT_SMALL]

        center_x   = theme.SCREEN_W // 2
        item_stride = theme.CAROUSEL_CENTER_W + theme.CAROUSEL_ITEM_GAP

        for i, (_, label, icon) in enumerate(_MODES):
            offset   = i - self._scroll_pos
            is_sel   = (i == self._selected)

            # Skip items that are completely off-screen
            if abs(offset) > 2.8:
                continue

            # Item dimensions scale by distance from center
            t = max(0.0, 1.0 - abs(offset))
            w = int(theme.CAROUSEL_FAR_W  + (theme.CAROUSEL_CENTER_W - theme.CAROUSEL_FAR_W)  * t)
            h = int(theme.CAROUSEL_FAR_H  + (theme.CAROUSEL_CENTER_H - theme.CAROUSEL_FAR_H)  * t)

            item_cx = center_x + int(offset * item_stride)
            item_x  = item_cx - w // 2
            item_y  = theme.CAROUSEL_CENTER_Y + (theme.CAROUSEL_CENTER_H - h) // 2

            # Box background
            bg_color = theme.ACCENT_DIM if is_sel else theme.BG_PANEL
            pygame.draw.rect(surface, bg_color, (item_x, item_y, w, h), border_radius=10)

            # Border: bright for selected, dim otherwise
            border_color = theme.ACCENT if is_sel else theme.BG_DARK
            pygame.draw.rect(surface, border_color, (item_x, item_y, w, h), 2, border_radius=10)

            # Icon (use large font for selected, medium for others)
            icon_font = font_large if is_sel else font_medium
            icon_surf = icon_font.render(icon, True, theme.TEXT_PRIMARY if is_sel else theme.TEXT_SECONDARY)
            icon_rect = icon_surf.get_rect(centerx=item_cx, centery=item_y + h // 2 - 8)
            surface.blit(icon_surf, icon_rect)

            # Label below box
            label_color = theme.HIGHLIGHT if is_sel else theme.TEXT_DIM
            label_surf  = font_small.render(label, True, label_color)
            label_rect  = label_surf.get_rect(centerx=item_cx, y=item_y + h + 6)
            surface.blit(label_surf, label_rect)

        # Quit confirmation hint
        if self._quit_armed:
            hint_surf = font_small.render("Press B again to quit", True, theme.ERROR_COLOR)
            hint_rect = hint_surf.get_rect(centerx=center_x, y=theme.SCREEN_H - 24)
            surface.blit(hint_surf, hint_rect)
        else:
            hint_surf = font_small.render("A: select   B: quit", True, theme.TEXT_DIM)
            hint_rect = hint_surf.get_rect(centerx=center_x, y=theme.SCREEN_H - 24)
            surface.blit(hint_surf, hint_rect)
