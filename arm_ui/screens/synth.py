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
        # Clear MIDI callbacks so notes don't fire on other screens
        self.app.midi_handler.set_callbacks(note_on=None, note_off=None)

    # ── MIDI callbacks ───────────────────────────────────────────────────────

    def _on_note_on(self, note: int, velocity: int) -> None:
        if self.app.synth_engine:
            self.app.synth_engine.note_on(note, velocity)

    def _on_note_off(self, note: int) -> None:
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
        bar_h   = 36
        bar_w   = 220
        left_x  = 8
        right_x = theme.SCREEN_W // 2 + 4
        row1_y  = 125
        row2_y  = 170

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

        font_large  = theme.FONTS[theme.FONT_LARGE]
        font_medium = theme.FONTS[theme.FONT_MEDIUM]
        font_small  = theme.FONTS[theme.FONT_SMALL]
        cx = theme.SCREEN_W // 2

        # ── Header row: navigation arrows + preset name ───────────────────
        arrow_surf = font_medium.render("◄", True, theme.ACCENT_DIM)
        surface.blit(arrow_surf, (8, 8))
        arrow_surf2 = font_medium.render("►", True, theme.ACCENT_DIM)
        surface.blit(arrow_surf2, (theme.SCREEN_W - arrow_surf2.get_width() - 8, 8))

        # Preset name (truncate long names)
        name = self._preset_name
        if len(name) > 22:
            name = name[:20] + "…"
        name_surf = font_large.render(name, True, theme.TEXT_PRIMARY)
        surface.blit(name_surf, name_surf.get_rect(centerx=cx, y=42))

        # ── Info row: origin badge + index counter ────────────────────────
        badge_color = theme.BADGE_BUILTIN if self._preset_origin == "built-in" else theme.BADGE_USER
        badge_text  = "Built-in" if self._preset_origin == "built-in" else "User"
        badge_surf  = font_small.render(badge_text, True, theme.TEXT_PRIMARY)
        badge_rect  = badge_surf.get_rect(x=10, y=93)
        pygame.draw.rect(surface, badge_color,
                         badge_rect.inflate(10, 6), border_radius=4)
        surface.blit(badge_surf, badge_rect)

        counter_text = f"{self._preset_index + 1} / {self._preset_count}"
        counter_surf = font_small.render(counter_text, True, theme.TEXT_SECONDARY)
        surface.blit(counter_surf,
                     counter_surf.get_rect(right=theme.SCREEN_W - 10, y=95))

        # ── Separator line ────────────────────────────────────────────────
        pygame.draw.line(surface, theme.BG_DARK,
                         (0, 117), (theme.SCREEN_W, 117))

        # ── Parameter bars ────────────────────────────────────────────────
        if self._bar_cutoff is not None:
            self._bar_cutoff.draw(surface)
            self._bar_resonance.draw(surface)
            self._bar_attack.draw(surface)
            self._bar_release.draw(surface)

        # ── Waveform + voice type text ────────────────────────────────────
        waveform   = self._current_params.get("waveform", "sine")
        voice_type = self._current_params.get("voice_type", "poly")
        wf_label   = _WAVEFORM_LABELS.get(waveform, waveform.title())
        info_text  = f"Wave: {wf_label}   Voice: {voice_type.title()}"
        info_surf  = font_small.render(info_text, True, theme.TEXT_SECONDARY)
        surface.blit(info_surf, info_surf.get_rect(centerx=cx, y=220))

        # ── Action buttons ────────────────────────────────────────────────
        btn_y   = 255
        btn_h   = max(theme.MIN_TOUCH, 40)
        btn_w   = 130
        spacing = (theme.SCREEN_W - btn_w * 3) // 4

        self._btn_random = pygame.Rect(spacing,              btn_y, btn_w, btn_h)
        self._btn_play   = pygame.Rect(spacing * 2 + btn_w,  btn_y, btn_w, btn_h)
        self._btn_save   = pygame.Rect(spacing * 3 + btn_w * 2, btn_y, btn_w, btn_h)

        for rect, label, is_active in [
            (self._btn_random, "Y: Random",    False),
            (self._btn_play,   "A: Play Note", self._note_active),
            (self._btn_save,   "X: Save",      False),
        ]:
            bg    = theme.ACCENT_DIM if is_active else theme.BG_PANEL
            border = theme.ACCENT    if is_active else theme.TEXT_DIM
            pygame.draw.rect(surface, bg,     rect, border_radius=6)
            pygame.draw.rect(surface, border, rect, 1, border_radius=6)
            lbl_surf = font_small.render(label, True, theme.TEXT_PRIMARY)
            surface.blit(lbl_surf, lbl_surf.get_rect(center=rect.center))

        # ── Status message (overlays bottom when present) ─────────────────
        if self._status_msg:
            color = theme.ERROR_COLOR if self._status_error else theme.SUCCESS
            st_surf = font_small.render(self._status_msg, True, color)
            surface.blit(st_surf, st_surf.get_rect(centerx=cx, y=btn_y + btn_h + 4))
