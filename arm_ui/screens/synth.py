# ABOUTME: Synth preset player screen for the ARM Pygame UI.
# ABOUTME: Browse, play, randomize, and save presets at 480x320 with controller or touch.

import math
import random
import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui.widgets.bar_display import BarDisplay
from arm_ui import theme
from gamepad.actions import GP

# Waveform display names (matches synth_engine waveform parameter values)
_WAVEFORM_LABELS = {
    "pure_sine": "Pure Sine",
    "sine":      "Sine",
    "square":    "Square",
    "sawtooth":  "Sawtooth",
    "triangle":  "Triangle",
}

# Layout constants
_NOTE_DURATION    = 0.5    # Seconds for test note auto-off
_SAVE_MSG_SECONDS = 2.0    # Duration of "Saved!" status message
_TEST_NOTE        = 60     # Middle C
_TEST_VELOCITY    = 80


def _normalize_cutoff(v: float) -> float:
    """Log-scale normalize cutoff (20-8000 Hz) to 0.0-1.0."""
    lo, hi = math.log(20), math.log(8000)
    return max(0.0, min(1.0, (math.log(max(20.0, v)) - lo) / (hi - lo)))


def _normalize_linear(v: float, lo: float, hi: float) -> float:
    """Linear normalize to 0.0-1.0."""
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


class SynthScreen(BaseScreen):
    """Synth preset player screen.

    Displays the current preset name, 4 key parameter bars, and
    action buttons. Designed for 480x320 with controller-primary navigation.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self._preset_index   = 0
        self._current_params = {}
        self._preset_name    = ""
        self._preset_origin  = "built-in"
        self._preset_count   = 0

        # Test note state
        self._note_timer  = 0.0
        self._note_active = False

        # Status message state
        self._status_msg   = ""
        self._status_timer = 0.0
        self._status_error = False

        # Parameter bar widgets (created in on_enter after theme fonts are ready)
        self._bar_cutoff    = None
        self._bar_resonance = None
        self._bar_attack    = None
        self._bar_release   = None

        # Touch button rects (built in draw)
        self._btn_random = pygame.Rect(0, 0, 0, 0)
        self._btn_play   = pygame.Rect(0, 0, 0, 0)
        self._btn_save   = pygame.Rect(0, 0, 0, 0)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def on_enter(self, **kwargs) -> None:
        self._preset_count = self.app.preset_manager.count()
        # Restore last-used preset from config
        last_fn = self.app.config_manager.get_last_preset()
        if last_fn:
            idx = self.app.preset_manager.find_index_by_filename(last_fn)
            if idx >= 0:
                self._preset_index = idx
        self._load_preset(self._preset_index)
        self._build_bars()
        self._register_gamepad()
        # Register MIDI callbacks so physical keyboard plays through the engine
        self.app.midi_handler.set_callbacks(
            note_on=self._on_note_on,
            note_off=self._on_note_off,
        )

    def on_exit(self) -> None:
        # Stop any playing test note when leaving
        if self._note_active:
            self.app.synth_engine.note_off(_TEST_NOTE, 0)
            self._note_active = False
        # Clear MIDI callbacks so notes don't fire on other screens.
        # set_callbacks() skips None args by design, so pass no-ops explicitly.
        self.app.midi_handler.set_callbacks(
            note_on=lambda n, v: None,
            note_off=lambda n, v=0: None,
        )

    # ── MIDI callbacks ───────────────────────────────────────────────────────

    def _on_note_on(self, note: int, velocity: int) -> None:
        if self.app.synth_engine:
            self.app.synth_engine.note_on(note, velocity)

    def _on_note_off(self, note: int, velocity: int = 0) -> None:
        if self.app.synth_engine:
            self.app.synth_engine.note_off(note, 0)

    # ── Gamepad ──────────────────────────────────────────────────────────────

    def _register_gamepad(self) -> None:
        gp = self.app.gamepad_handler
        gp.set_button_callback(GP.DPAD_LEFT,  self._prev_preset)
        gp.set_button_callback(GP.DPAD_RIGHT, self._next_preset)
        gp.set_button_callback(GP.LB,         self._jump_back_10)
        gp.set_button_callback(GP.RB,         self._jump_fwd_10)
        gp.set_button_callback(GP.CONFIRM,    self._play_test_note)
        gp.set_button_callback(GP.ACTION_2,   self._randomize)
        gp.set_button_callback(GP.ACTION_1,   self._save_preset)
        gp.set_button_callback(GP.BACK,       lambda: self.app.goto("main_menu"))

    # ── Preset navigation ────────────────────────────────────────────────────

    def _prev_preset(self) -> None:
        count = self.app.preset_manager.count()
        self._preset_index = (self._preset_index - 1) % count
        self._load_preset(self._preset_index)
        self.app.request_redraw()

    def _next_preset(self) -> None:
        count = self.app.preset_manager.count()
        self._preset_index = (self._preset_index + 1) % count
        self._load_preset(self._preset_index)
        self.app.request_redraw()

    def _jump_back_10(self) -> None:
        count = self.app.preset_manager.count()
        self._preset_index = (self._preset_index - 10) % count
        self._load_preset(self._preset_index)
        self.app.request_redraw()

    def _jump_fwd_10(self) -> None:
        count = self.app.preset_manager.count()
        self._preset_index = (self._preset_index + 10) % count
        self._load_preset(self._preset_index)
        self.app.request_redraw()

    def _load_preset(self, index: int) -> None:
        """Load preset at index, push params to engine, update bar displays."""
        from music.preset_manager import DEFAULT_PARAMS

        pm = self.app.preset_manager
        preset = pm.get(index)
        if preset is None:
            return

        # Merge with defaults so old presets without new keys still work
        merged = dict(DEFAULT_PARAMS)
        merged.update(preset.params)

        self._current_params = merged
        self._preset_name    = preset.name
        self._preset_origin  = getattr(preset, "origin", "built-in")
        self._preset_count   = pm.count()

        self.app.synth_engine.update_parameters(**merged)
        self.app.config_manager.set_last_preset(preset.filename)

        self._update_bars()

    # ── Test note ────────────────────────────────────────────────────────────

    def _play_test_note(self) -> None:
        if self._note_active:
            self.app.synth_engine.note_off(_TEST_NOTE, 0)
        self.app.synth_engine.note_on(_TEST_NOTE, _TEST_VELOCITY)
        self._note_active = True
        self._note_timer  = _NOTE_DURATION
        self.app.request_redraw()

    # ── Randomize ────────────────────────────────────────────────────────────

    def _randomize(self) -> None:
        """Generate musically useful random parameters (mirrors SynthMode.action_randomize)."""
        params = dict(self._current_params)

        params["waveform"]  = random.choice(["pure_sine", "sine", "square", "sawtooth", "triangle"])
        params["octave"]    = random.choices([-2, -1, 0, 1, 2], weights=[1, 2, 4, 2, 1])[0]
        params["amp_level"] = 0.95
        params["cutoff"]    = round(10 ** random.uniform(math.log10(200), math.log10(18000)), 1)
        params["resonance"] = round(random.choices(
            [random.uniform(0.0, 0.3), random.uniform(0.3, 0.65), random.uniform(0.65, 1.0)],
            weights=[50, 35, 15],
        )[0], 2)
        params["voice_type"] = random.choice(["mono", "poly", "unison"])
        params["attack"]     = round(10 ** random.uniform(math.log10(0.008), math.log10(2.0)), 4)
        params["decay"]      = round(10 ** random.uniform(math.log10(0.005), math.log10(2.0)), 4)
        params["sustain"]    = round(random.choices(
            [random.uniform(0.0, 0.3), random.uniform(0.3, 0.7), random.uniform(0.7, 1.0)],
            weights=[25, 35, 40],
        )[0], 2)
        params["release"]   = round(10 ** random.uniform(math.log10(0.008), math.log10(3.0)), 4)
        params["intensity"] = round(random.uniform(0.40, 1.0), 2)
        params["key_tracking"] = round(random.uniform(0.0, 1.0), 2)
        params["feg_amount"] = round(random.uniform(0.5, 1.0), 2)

        self._current_params = params
        self._preset_name    = "Random"
        self._preset_origin  = "user"

        # Mute gate before param update to avoid clicks on held notes
        self.app.synth_engine.midi_event_queue.put({"type": "mute_gate"})
        self.app.synth_engine.update_parameters(**params)
        self._update_bars()
        self._show_status("Randomized!", error=False)

    # ── Save ─────────────────────────────────────────────────────────────────

    def _save_preset(self) -> None:
        try:
            preset = self.app.preset_manager.save_new(self._current_params)
            self.app.preset_manager.reload()
            self._preset_count = self.app.preset_manager.count()
            idx = self.app.preset_manager.find_index_by_filename(preset.filename)
            if idx >= 0:
                self._preset_index = idx
            self._preset_name   = preset.name
            self._preset_origin = "user"
            self.app.config_manager.set_last_preset(preset.filename)
            self._show_status(f"Saved: {preset.name[:22]}", error=False)
        except Exception as exc:
            self._show_status(f"Save failed: {str(exc)[:20]}", error=True)

    # ── Status messages ──────────────────────────────────────────────────────

    def _show_status(self, msg: str, error: bool = False) -> None:
        self._status_msg   = msg
        self._status_timer = _SAVE_MSG_SECONDS
        self._status_error = error

    # ── Bar helpers ───────────────────────────────────────────────────────────

    def _build_bars(self) -> None:
        """Create BarDisplay widgets at their screen positions."""
        bar_h   = 34
        bar_w   = 228
        left_x  = 6
        right_x = theme.SCREEN_W // 2 + 6
        row1_y  = 82
        row2_y  = 124

        self._bar_cutoff    = BarDisplay(pygame.Rect(left_x,  row1_y, bar_w, bar_h), "Cutoff")
        self._bar_resonance = BarDisplay(pygame.Rect(right_x, row1_y, bar_w, bar_h), "Resonance")
        self._bar_attack    = BarDisplay(pygame.Rect(left_x,  row2_y, bar_w, bar_h), "Attack")
        self._bar_release   = BarDisplay(pygame.Rect(right_x, row2_y, bar_w, bar_h), "Release")

    def _update_bars(self) -> None:
        """Sync bar values from current params."""
        if self._bar_cutoff is None:
            return
        p = self._current_params
        self._bar_cutoff.set_value(_normalize_cutoff(p.get("cutoff", 2000.0)))
        self._bar_resonance.set_value(_normalize_linear(p.get("resonance", 0.3), 0.0, 1.0))
        self._bar_attack.set_value(_normalize_linear(p.get("attack", 0.01), 0.0, 4.0))
        self._bar_release.set_value(_normalize_linear(p.get("release", 0.1), 0.0, 4.0))

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        # Auto-off test note
        if self._note_active:
            self._note_timer -= dt
            if self._note_timer <= 0.0:
                self.app.synth_engine.note_off(_TEST_NOTE, 0)
                self._note_active = False
            self.app.request_redraw()

        # Status message countdown
        if self._status_timer > 0.0:
            self._status_timer -= dt
            if self._status_timer <= 0.0:
                self._status_msg = ""
            self.app.request_redraw()

    # ── Draw ──────────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            self._handle_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self._handle_touch(event.pos)

    def _handle_key(self, key: int) -> None:
        if key in (pygame.K_LEFT,  pygame.K_a):
            self._prev_preset()
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._next_preset()
        elif key == pygame.K_COMMA:
            self._jump_back_10()
        elif key == pygame.K_PERIOD:
            self._jump_fwd_10()
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._play_test_note()
        elif key == pygame.K_r:
            self._randomize()
        elif key == pygame.K_s:
            self._save_preset()
        elif key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.app.goto("main_menu")

    def _handle_touch(self, pos: tuple) -> None:
        if self._btn_random.collidepoint(pos):
            self._randomize()
        elif self._btn_play.collidepoint(pos):
            self._play_test_note()
        elif self._btn_save.collidepoint(pos):
            self._save_preset()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(theme.BG_COLOR)
        cx = theme.SCREEN_W // 2

        # ── Header row: screen label left, preset counter right ───────────
        scr_lbl = theme.txt(theme.FONT_TINY, "SYNTH", theme.ACCENT)
        surface.blit(scr_lbl, (6, 4))

        counter = theme.txt(theme.FONT_TINY,
                            f"{self._preset_index + 1}/{self._preset_count}",
                            theme.TEXT_DIM)
        surface.blit(counter, (theme.SCREEN_W - counter.get_width() - 6, 4))

        # ── Separator ─────────────────────────────────────────────────────
        pygame.draw.line(surface, theme.SEPARATOR, (0, 16), (theme.SCREEN_W, 16))

        # ── Origin badge + preset name ────────────────────────────────────
        origin_lbl = "BUILT-IN" if self._preset_origin == "built-in" else "USER"
        origin_col = theme.TEXT_DIM if self._preset_origin == "built-in" else theme.HIGHLIGHT
        orig = theme.txt(theme.FONT_TINY, origin_lbl, origin_col)
        surface.blit(orig, (6, 21))

        # Nav arrows flanking the preset name area
        arrow_l = theme.txt(theme.FONT_TINY, "<", theme.TEXT_DIM)
        arrow_r = theme.txt(theme.FONT_TINY, ">", theme.TEXT_DIM)
        surface.blit(arrow_l, (6, 36))
        surface.blit(arrow_r, (theme.SCREEN_W - arrow_r.get_width() - 6, 36))

        name = self._preset_name[:22]
        name_surf = theme.txt(theme.FONT_LARGE, name.upper(), theme.TEXT_PRIMARY)
        surface.blit(name_surf, name_surf.get_rect(centerx=cx, y=28))

        # ── Separator ─────────────────────────────────────────────────────
        pygame.draw.line(surface, theme.SEPARATOR, (0, 62), (theme.SCREEN_W, 62))

        # ── Waveform + voice info row ─────────────────────────────────────
        waveform   = self._current_params.get("waveform", "sine")
        voice_type = self._current_params.get("voice_type", "poly")
        wf_label   = _WAVEFORM_LABELS.get(waveform, waveform.upper())

        wf_surf = theme.txt(theme.FONT_TINY,
                            f"WAVE  {wf_label.upper()[:3]}",
                            theme.TEXT_SECONDARY)
        vc_surf = theme.txt(theme.FONT_TINY,
                            f"VOICE  {voice_type.upper()[:4]}",
                            theme.TEXT_SECONDARY)
        surface.blit(wf_surf, (6, 67))
        surface.blit(vc_surf, (theme.SCREEN_W - vc_surf.get_width() - 6, 67))

        # ── Parameter bars ────────────────────────────────────────────────
        if self._bar_cutoff is not None:
            self._bar_cutoff.draw(surface)
            self._bar_resonance.draw(surface)
            self._bar_attack.draw(surface)
            self._bar_release.draw(surface)

        # ── Separator above buttons ────────────────────────────────────────
        pygame.draw.line(surface, theme.SEPARATOR, (0, 216), (theme.SCREEN_W, 216))

        # ── Action buttons - Elektron style ───────────────────────────────
        btn_y   = 224
        btn_h   = 38
        btn_w   = 128
        spacing = (theme.SCREEN_W - btn_w * 3) // 4

        self._btn_random = pygame.Rect(spacing,                  btn_y, btn_w, btn_h)
        self._btn_play   = pygame.Rect(spacing * 2 + btn_w,      btn_y, btn_w, btn_h)
        self._btn_save   = pygame.Rect(spacing * 3 + btn_w * 2,  btn_y, btn_w, btn_h)

        for rect, label, key_hint, is_active in [
            (self._btn_random, "RANDOM", "Y", False),
            (self._btn_play,   "PLAY",   "A", self._note_active),
            (self._btn_save,   "SAVE",   "X", False),
        ]:
            # Button background
            pygame.draw.rect(surface, theme.BG_PANEL, rect)

            if is_active:
                # Active state: solid green border, green corner marks
                pygame.draw.rect(surface, theme.ACCENT, rect, 1)
                theme.draw_corner_marks(surface, theme.ACCENT, rect, size=4)
                lbl_col = theme.ACCENT
            else:
                # Inactive: dotted dim border, white label
                theme.draw_dotted_rect(surface, theme.ACCENT_DIM, rect, step=4)
                lbl_col = theme.TEXT_PRIMARY

            lbl = theme.txt(theme.FONT_TINY, label, lbl_col)
            surface.blit(lbl, lbl.get_rect(centerx=rect.centerx, y=rect.y + 5))
            hint = theme.txt(theme.FONT_TINY, f"[{key_hint}]", theme.TEXT_DIM)
            surface.blit(hint, hint.get_rect(centerx=rect.centerx, y=rect.y + 20))

        # ── Status / hint bar ─────────────────────────────────────────────
        pygame.draw.line(surface, theme.SEPARATOR,
                         (0, theme.SCREEN_H - 18), (theme.SCREEN_W, theme.SCREEN_H - 18))
        if self._status_msg:
            color   = theme.ERROR_COLOR if self._status_error else theme.SUCCESS
            st_surf = theme.txt(theme.FONT_TINY, self._status_msg, color)
            surface.blit(st_surf, st_surf.get_rect(centerx=cx, y=theme.SCREEN_H - 13))
        else:
            hint = theme.txt(theme.FONT_TINY,
                             "L/R: preset   ,/.: jump10   Esc: back",
                             theme.TEXT_DIM)
            surface.blit(hint, hint.get_rect(centerx=cx, y=theme.SCREEN_H - 13))
