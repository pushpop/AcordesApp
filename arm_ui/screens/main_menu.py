# ABOUTME: Main menu carousel screen for the ARM Pygame UI.
# ABOUTME: Shows 6 mode icons in a pixel-art grid, navigated by D-pad, keyboard, or touch.

import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui import theme
from gamepad.actions import GP

# Mode definitions: (screen_name, display_label, icon_character)
_MODES = [
    ("piano",      "PIANO",  "♪"),
    ("synth",      "SYNTH",  "~"),
    ("metronome",  "METRO",  "M"),
    ("tambor",     "TAMBOR", "●"),
    ("compendium", "CHORDS", "♫"),
    ("config",     "CONFIG", "⚙"),
]

_QUIT_CONFIRM = False  # Module-level default; instance state is per-object


class MainMenuScreen(BaseScreen):
    """Horizontal carousel main menu with Elektron-inspired pixel art style."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._selected   = 0
        self._scroll_pos = 0.0
        self._quit_armed = False

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
        self.app.goto(_MODES[self._selected][0])

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
        x, y = pos
        center_x    = theme.SCREEN_W // 2
        item_stride = theme.CAROUSEL_CENTER_W + theme.CAROUSEL_ITEM_GAP
        for i, _ in enumerate(_MODES):
            offset = i - self._selected
            item_cx = center_x + int(offset * item_stride)
            item_w  = theme.CAROUSEL_CENTER_W if i == self._selected else theme.CAROUSEL_SIDE_W
            item_h  = theme.CAROUSEL_CENTER_H if i == self._selected else theme.CAROUSEL_SIDE_H
            item_x  = item_cx - item_w // 2
            item_y  = theme.CAROUSEL_CENTER_Y
            if pygame.Rect(item_x, item_y, item_w, item_h).collidepoint(x, y):
                if i == self._selected:
                    self._select()
                else:
                    self._selected = i
                    self.app.request_redraw()
                return

    def update(self, dt: float) -> None:
        self._scroll_pos = float(self._selected)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(theme.BG_COLOR)

        center_x    = theme.SCREEN_W // 2
        item_stride = theme.CAROUSEL_CENTER_W + theme.CAROUSEL_ITEM_GAP

        for i, (_, label, icon) in enumerate(_MODES):
            offset = i - self._scroll_pos
            is_sel = (i == self._selected)

            if abs(offset) > 2.8:
                continue

            # Size scales with distance from center
            t = max(0.0, 1.0 - abs(offset))
            w = int(theme.CAROUSEL_FAR_W + (theme.CAROUSEL_CENTER_W - theme.CAROUSEL_FAR_W) * t)
            h = int(theme.CAROUSEL_FAR_H + (theme.CAROUSEL_CENTER_H - theme.CAROUSEL_FAR_H) * t)

            item_cx = center_x + int(offset * item_stride)
            item_x  = item_cx - w // 2
            item_y  = theme.CAROUSEL_CENTER_Y + (theme.CAROUSEL_CENTER_H - h) // 2

            rect = (item_x, item_y, w, h)

            # Panel fill
            pygame.draw.rect(surface, theme.BG_PANEL, rect)

            if is_sel:
                # Selected: solid orange border + green corner marks
                pygame.draw.rect(surface, theme.HIGHLIGHT, rect, 1)
                theme.draw_corner_marks(surface, theme.ACCENT, rect, size=5)
            else:
                # Inactive: dotted dim green border
                theme.draw_dotted_rect(surface, theme.ACCENT_DIM, rect, step=4)

            # Icon - green for selected, dim for others
            icon_size  = theme.FONT_LARGE if is_sel else theme.FONT_MEDIUM
            icon_color = theme.ACCENT if is_sel else theme.TEXT_DIM
            icon_surf  = theme.txt(icon_size, icon, icon_color)
            icon_rect  = icon_surf.get_rect(centerx=item_cx,
                                            centery=item_y + h // 2 - 6)
            surface.blit(icon_surf, icon_rect)

            # Label below box - white for selected, dim for others
            lbl_color = theme.TEXT_PRIMARY if is_sel else theme.TEXT_DIM
            lbl_surf  = theme.txt(theme.FONT_TINY, label, lbl_color)
            lbl_rect  = lbl_surf.get_rect(centerx=item_cx, y=item_y + h + 5)
            surface.blit(lbl_surf, lbl_rect)

        # Title bar at very top
        title = theme.txt(theme.FONT_TINY, "ACORDES", theme.ACCENT)
        surface.blit(title, (6, 4))
        ver = theme.txt(theme.FONT_TINY, "OStra", theme.TEXT_DIM)
        surface.blit(ver, (theme.SCREEN_W - ver.get_width() - 6, 4))

        # Separator above hint bar
        pygame.draw.line(surface, theme.SEPARATOR,
                         (0, theme.SCREEN_H - 22), (theme.SCREEN_W, theme.SCREEN_H - 22))

        # Hint bar
        if self._quit_armed:
            hint = theme.txt(theme.FONT_TINY, ">> PRESS ESC AGAIN TO QUIT <<", theme.ERROR_COLOR)
        else:
            hint = theme.txt(theme.FONT_TINY,
                             "L/R: navigate   Enter: select   Esc: quit",
                             theme.TEXT_DIM)
        surface.blit(hint, hint.get_rect(centerx=theme.SCREEN_W // 2,
                                         y=theme.SCREEN_H - 16))
