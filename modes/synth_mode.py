"""Synth mode - Polyphonic synthesizer interface with preset management."""
import math
import random
import re
from typing import TYPE_CHECKING, Optional

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

from music.synth_engine import SynthEngine
from music.preset_manager import PresetManager, Preset, DEFAULT_PARAMS, PARAM_KEYS
from components.header_widget import HeaderWidget

if TYPE_CHECKING:
    from midi.input_handler import MIDIInputHandler
    from config_manager import ConfigManager


class SynthMode(Widget):
    """Widget for polyphonic synthesizer interface with preset management."""

    can_focus = True

    BINDINGS = [
        Binding("full_stop", "preset_next", "Preset next", show=False),
        Binding("comma", "preset_prev", "Preset prev", show=False),
        Binding("ctrl+n", "save_preset_new", "Save New Preset", show=False),
        Binding("ctrl+s", "save_preset_overwrite", "Update Preset", show=False),
        Binding("w", "toggle_waveform", "Waveform", show=False),
        Binding("s", "adjust_octave('up')", "Oct+", show=False),
        Binding("x", "adjust_octave('down')", "Oct-", show=False),
        Binding("up", "adjust_volume('up')", "Vol+", show=False),
        Binding("down", "adjust_volume('down')", "Vol-", show=False),
        Binding("left", "adjust_cutoff('left')", "Cut-", show=False),
        Binding("right", "adjust_cutoff('right')", "Cut+", show=False),
        Binding("q", "adjust_resonance('up')", "Res+", show=False),
        Binding("a", "adjust_resonance('down')", "Res-", show=False),
        Binding("e", "adjust_attack('up')", "Atk+", show=False),
        Binding("d", "adjust_attack('down')", "Atk-", show=False),
        Binding("r", "adjust_decay('up')", "Dec+", show=False),
        Binding("f", "adjust_decay('down')", "Dec-", show=False),
        Binding("t", "adjust_sustain('up')", "Sus+", show=False),
        Binding("g", "adjust_sustain('down')", "Sus-", show=False),
        Binding("y", "adjust_release('up')", "Rel+", show=False),
        Binding("h", "adjust_release('down')", "Rel-", show=False),
        Binding("u", "adjust_intensity('up')", "Int+", show=False),
        Binding("j", "adjust_intensity('down')", "Int-", show=False),
        Binding("space", "panic", "Panic (All Notes Off)", show=False),
        Binding("minus", "randomize", "🎲 Randomize", show=False),
    ]

    CSS = """
    SynthMode {
        width: 100%;
        height: 100%;
        layout: vertical;
        padding: 0;
        margin: 0;
        align: center top;
    }

    #synth-container {
        layout: horizontal;
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }

    #preset-bar {
        width: 100%;
        height: 3;
        background: #0d1a0d;
        color: #00ff00;
        border: round #00ff00;
        text-align: center;
        content-align: center middle;
        padding: 0 2;
        margin: 0;
    }

    #controls-help {
        width: 100%;
        height: auto;
        background: #1a1a1a;
        border-top: heavy #00ff00;
        padding: 0;
        margin: 0;
        text-align: center;
        content-align: center middle;
    }

    #oscillator-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #1a1a1a;
        padding: 0;
        margin: 0;
    }

    #filter-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #1a1a1a;
        padding: 0;
        margin: 0;
    }

    #envelope-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #1a1a1a;
        padding: 0;
        margin: 0;
    }

    #mixer-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #1a1a1a;
        padding: 0;
        margin: 0;
    }

    .section-label {
        color: #00ff00;
        text-style: bold;
        padding: 0;
        margin: 0;
        width: 100%;
        height: 1;
        text-align: left;
    }

    .control-label {
        color: #888888;
        width: 100%;
        height: 1;
        text-align: left;
        padding: 0;
        margin: 0;
    }

    .control-value {
        color: #ffffff;
        text-style: bold;
        width: 100%;
        height: auto;
        text-align: left;
        padding: 0;
        margin: 0;
    }
    """

    def __init__(
        self,
        midi_handler,
        synth_engine,
        config_manager,
    ):
        super().__init__()
        self.midi_handler = midi_handler
        self.synth_engine = synth_engine
        self.config_manager = config_manager

        self.preset_manager = PresetManager()
        self._current_preset: Optional[Preset] = None
        self._preset_index: int = -1
        self._dirty: bool = False

        params = self._load_initial_params()
        self.waveform   = params["waveform"]
        self.octave     = params["octave"]
        self.amp_level  = params["amp_level"]
        self.cutoff     = params["cutoff"]
        self.resonance  = params["resonance"]
        self.attack     = params["attack"]
        self.decay      = params["decay"]
        self.sustain    = params["sustain"]
        self.release    = params["release"]
        self.intensity  = params["intensity"]

        self.waveform_display   = None
        self.octave_display     = None
        self.amp_display        = None
        self.cutoff_display     = None
        self.resonance_display  = None
        self.attack_display     = None
        self.decay_display      = None
        self.sustain_display    = None
        self.release_display    = None
        self.intensity_display  = None
        self.header             = None
        self.current_note: Optional[int] = None

    def _load_initial_params(self) -> dict:
        last_file = self.config_manager.get_last_preset()
        if last_file:
            idx = self.preset_manager.find_index_by_filename(last_file)
            if idx >= 0:
                preset = self.preset_manager.get(idx)
                self._current_preset = preset
                self._preset_index = idx
                self._dirty = False
                return self.preset_manager.extract_params(preset)
        state = self.config_manager.get_synth_state()
        if state:
            out = dict(DEFAULT_PARAMS)
            out.update({k: state[k] for k in PARAM_KEYS if k in state})
            self._dirty = True
            return out
        return dict(DEFAULT_PARAMS)

    def compose(self):
        self.header = HeaderWidget(
            title="S Y N T H   M O D E",
            subtitle=self._get_status_text(),
            is_big=False,
        )
        yield self.header

        # ── PRESET BAR (above synth boxes) ──────────────────────────
        yield Static(self._fmt_preset_bar(), id="preset-bar")

        with Horizontal(id="synth-container"):
            with Vertical(id="oscillator-section"):
                yield Label(self._section_top("OSCILLATOR"), classes="section-label")
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("Wave [W]"), classes="control-label")
                self.waveform_display = Label(self._fmt_waveform(), classes="control-value", id="waveform-display")
                yield self.waveform_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("Oct [S/X]"), classes="control-label")
                self.octave_display = Label(self._fmt_octave(), classes="control-value", id="octave-display")
                yield self.octave_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._section_bottom(), classes="section-label")

            with Vertical(id="filter-section"):
                yield Label(self._section_top("FILTER"), classes="section-label")
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("Cut [left/right]"), classes="control-label")
                self.cutoff_display = Label(self._fmt_cutoff(), classes="control-value", id="cutoff-display")
                yield self.cutoff_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("Res [Q/A]"), classes="control-label")
                self.resonance_display = Label(self._fmt_resonance(), classes="control-value", id="resonance-display")
                yield self.resonance_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._section_bottom(), classes="section-label")

            with Vertical(id="envelope-section"):
                yield Label(self._section_top("ENVELOPE"), classes="section-label")
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("A [E/D]"), classes="control-label")
                self.attack_display = Label(self._fmt_time(self.attack), classes="control-value", id="attack-display")
                yield self.attack_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("D [R/F]"), classes="control-label")
                self.decay_display = Label(self._fmt_time(self.decay), classes="control-value", id="decay-display")
                yield self.decay_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("S [T/G]"), classes="control-label")
                self.sustain_display = Label(
                    self._fmt_slider(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"),
                    classes="control-value", id="sustain-display")
                yield self.sustain_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("R [Y/H]"), classes="control-label")
                self.release_display = Label(self._fmt_time(self.release), classes="control-value", id="release-display")
                yield self.release_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("Int [U/J]"), classes="control-label")
                self.intensity_display = Label(
                    self._fmt_slider(self.intensity, 0.0, 1.0, f"{int(self.intensity * 100)}%"),
                    classes="control-value", id="intensity-display")
                yield self.intensity_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._section_bottom(), classes="section-label")

            with Vertical(id="mixer-section"):
                yield Label(self._section_top("AMP"), classes="section-label")
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._box_line("Amp [up/down]"), classes="control-label")
                yield Label(self._empty_line(), classes="section-label")
                self.amp_display = Label(
                    self._fmt_slider(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%"),
                    classes="control-value", id="amp-display")
                yield self.amp_display
                yield Label(self._empty_line(), classes="section-label")
                yield Label(self._section_bottom(), classes="section-label")

        # ── CONTROLS HELP ────────────────────────────────────────────
        yield Static(
            "[bold #00ff00]PRESET:[/] [,] Prev  [.] Next  [Ctrl+N] Save New  [Ctrl+S] Update  "
            "[bold #00ff00]SYNTH:[/] [W] Wave [S/X] Oct [↑/↓] Amp [←/→] Cut [Q/A] Res "
            "[E/D] Atk [R/F] Dec [T/G] Sus [Y/H] Rel [U/J] Int  "
            "[bold yellow][-] 🎲 Randomize[/]  [SPACE] Panic",
            id="controls-help",
        )

    # ── Lifecycle ────────────────────────────────────────────────

    def on_mount(self):
        self.focus()
        self.midi_handler.set_callbacks(
            note_on=self._on_note_on,
            note_off=self._on_note_off,
            pitch_bend=self._on_pitch_bend,
            control_change=self._on_control_change,
        )
        self.set_interval(0.01, self._poll_midi)
        self._push_params_to_engine()
        self._update_preset_ui()

    def on_unmount(self):
        """Save state when switching away — do NOT close the shared engine."""
        self._autosave_state()

    # ── MIDI plumbing ────────────────────────────────────────────

    def _poll_midi(self):
        if self.midi_handler.is_device_open():
            self.midi_handler.poll_messages()

    def _on_note_on(self, note: int, velocity: int):
        self.current_note = note
        self.synth_engine.note_on(note, velocity)
        if self.header:
            note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            oct_ = (note // 12) - 1
            name = note_names[note % 12]
            self.header.update_subtitle(
                f"🎵 Playing: {name}{oct_} (MIDI {note}) • Vel: {velocity}"
            )

    def _on_note_off(self, note: int):
        self.synth_engine.note_off(note)
        if self.current_note == note:
            self.current_note = None
            self._update_preset_ui()

    def _on_pitch_bend(self, value: int):
        self.synth_engine.pitch_bend_change(value)

    def _on_control_change(self, controller: int, value: int):
        if controller == 1:
            self.synth_engine.modulation_change(value)

    # ── Preset actions ───────────────────────────────────────────

    def action_preset_next(self):
        if not self.preset_manager.count():
            return
        self._preset_index = (self._preset_index + 1) % self.preset_manager.count()
        self._load_preset_at_index(self._preset_index)

    def action_preset_prev(self):
        if not self.preset_manager.count():
            return
        self._preset_index = (self._preset_index - 1) % self.preset_manager.count()
        self._load_preset_at_index(self._preset_index)

    def action_save_preset_new(self):
        params = self._current_params()
        preset = self.preset_manager.save_new(params)
        self._current_preset = preset
        self._preset_index = self.preset_manager.find_index_by_filename(preset.filename)
        self._dirty = False
        self.config_manager.set_last_preset(preset.filename)
        self._update_preset_ui()
        self.app.notify(f'💾 Saved: "{preset.name}"', timeout=3)

    def action_save_preset_overwrite(self):
        if self._current_preset is None:
            self.app.notify(
                "⚠ No preset loaded — use [P] to save a new one",
                severity="warning", timeout=3
            )
            return
        params = self._current_params()
        preset = self.preset_manager.save_overwrite(self._current_preset, params)
        self._current_preset = preset
        self._dirty = False
        self.config_manager.set_last_preset(preset.filename)
        self._update_preset_ui()
        self.app.notify(f'✅ Updated: "{preset.name}"', timeout=3)

    def _load_preset_at_index(self, index: int):
        preset = self.preset_manager.get(index)
        if preset is None:
            return
        self._current_preset = preset
        params = self.preset_manager.extract_params(preset)
        self._apply_params(params)
        self._dirty = False
        self.config_manager.set_last_preset(preset.filename)
        self._update_preset_ui()

    # ── Parameter helpers ────────────────────────────────────────

    def _apply_params(self, params: dict):
        self.waveform   = params.get("waveform",  self.waveform)
        self.octave     = params.get("octave",    self.octave)
        self.amp_level  = params.get("amp_level", self.amp_level)
        self.cutoff     = params.get("cutoff",    self.cutoff)
        self.resonance  = params.get("resonance", self.resonance)
        self.attack     = params.get("attack",    self.attack)
        self.decay      = params.get("decay",     self.decay)
        self.sustain    = params.get("sustain",   self.sustain)
        self.release    = params.get("release",   self.release)
        self.intensity  = params.get("intensity", self.intensity)
        self._push_params_to_engine()
        self._refresh_all_displays()

    def _push_params_to_engine(self):
        self.synth_engine.update_parameters(
            waveform=self.waveform,
            octave=self.octave,
            amp_level=self.amp_level,
            cutoff=self.cutoff,
            resonance=self.resonance,
            attack=self.attack,
            decay=self.decay,
            sustain=self.sustain,
            release=self.release,
            intensity=self.intensity,
        )

    def _current_params(self) -> dict:
        return {
            "waveform":  self.waveform,
            "octave":    self.octave,
            "amp_level": self.amp_level,
            "cutoff":    self.cutoff,
            "resonance": self.resonance,
            "attack":    self.attack,
            "decay":     self.decay,
            "sustain":   self.sustain,
            "release":   self.release,
            "intensity": self.intensity,
        }

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self._update_preset_ui()

    def _autosave_state(self):
        self.config_manager.set_synth_state(self._current_params())

    # ── UI update helpers ────────────────────────────────────────

    def _get_status_text(self) -> str:
        if self.synth_engine.is_available():
            if self.midi_handler.is_device_open():
                return "🎵 Synth ready - Play some notes!"
            return "⚠ No MIDI device - select one in Config (C)"
        return "⚠ Audio not available (install pyaudio)"

    def _fmt_preset_bar(self) -> str:
        """Render the preset bar content.

        The surrounding box is drawn by CSS border on #preset-bar,
        so this method returns only the inner text — no hand-drawn characters.
        """
        total = self.preset_manager.count()
        if self._current_preset and total:
            idx = self._preset_index + 1
            dirty = "  [bold yellow]*[/]" if self._dirty else ""
            return (
                f"[dim],[/][bold #00ff00]◄ PRESET ►[/][dim].[/]"
                f"   [dim][{idx}/{total}][/]"
                f"  [bold white]{self._current_preset.name}[/]{dirty}"
            )
        elif self._dirty:
            return (
                f"[dim],[/][bold #00ff00]◄ PRESET ►[/][dim].[/]"
                f"   [bold yellow]unsaved *[/]"
            )
        else:
            return (
                f"[dim],[/][bold #00ff00]◄ PRESET ►[/][dim].[/]"
                f"   [dim]— no preset loaded —[/]"
            )

    def _update_preset_ui(self):
        """Refresh both the preset bar and the header subtitle."""
        # Update preset bar widget
        try:
            bar = self.query_one("#preset-bar", Static)
            bar.update(self._fmt_preset_bar())
        except Exception:
            pass

        # Update header subtitle
        if self.header:
            total = self.preset_manager.count()
            if self._current_preset and total:
                idx = self._preset_index + 1
                dirty_mark = " *" if self._dirty else ""
                self.header.update_subtitle(
                    f"[{idx}/{total}] {self._current_preset.name}{dirty_mark}"
                )
            elif self._dirty:
                self.header.update_subtitle(f"[unsaved *]  —  {self._get_status_text()}")
            else:
                self.header.update_subtitle(self._get_status_text())

    # ── Keyboard actions ─────────────────────────────────────────

    def action_toggle_waveform(self):
        order = ["sine", "square", "sawtooth", "triangle"]
        self.waveform = order[(order.index(self.waveform) + 1) % len(order)]
        self.synth_engine.update_parameters(waveform=self.waveform)
        if self.waveform_display:
            self.waveform_display.update(self._fmt_waveform())
        self._mark_dirty()
        self._autosave_state()

    def action_adjust_octave(self, direction: str = "up"):
        self.octave = min(2, self.octave + 1) if direction == "up" else max(-2, self.octave - 1)
        self.synth_engine.update_parameters(octave=self.octave)
        if self.octave_display:
            self.octave_display.update(self._fmt_octave())
        self._mark_dirty()
        self._autosave_state()

    def action_adjust_volume(self, direction: str = "up"):
        self.amp_level = min(1.0, self.amp_level + 0.05) if direction == "up" else max(0.0, self.amp_level - 0.05)
        self.synth_engine.update_parameters(amp_level=self.amp_level)
        if self.amp_display:
            self.amp_display.update(
                self._fmt_slider(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%")
            )
        self._mark_dirty()
        self._autosave_state()

    def action_adjust_cutoff(self, direction: str = "right"):
        self.cutoff = min(20000.0, self.cutoff * 1.1) if direction == "right" else max(20.0, self.cutoff / 1.1)
        self.synth_engine.update_parameters(cutoff=self.cutoff)
        if self.cutoff_display:
            self.cutoff_display.update(self._fmt_cutoff())
        self._mark_dirty()
        self._autosave_state()

    def action_adjust_resonance(self, direction: str = "up"):
        self.resonance = min(0.9, self.resonance + 0.05) if direction == "up" else max(0.0, self.resonance - 0.05)
        self.synth_engine.update_parameters(resonance=self.resonance)
        if self.resonance_display:
            self.resonance_display.update(self._fmt_resonance())
        self._mark_dirty()
        self._autosave_state()

    def action_adjust_attack(self, direction: str = "up"):
        self.attack = min(5.0, self.attack * 1.15) if direction == "up" else max(0.001, self.attack / 1.15)
        self.synth_engine.update_parameters(attack=self.attack)
        if self.attack_display:
            self.attack_display.update(self._fmt_time(self.attack))
        self._mark_dirty()
        self._autosave_state()

    def action_adjust_decay(self, direction: str = "up"):
        self.decay = min(5.0, self.decay * 1.15) if direction == "up" else max(0.001, self.decay / 1.15)
        self.synth_engine.update_parameters(decay=self.decay)
        if self.decay_display:
            self.decay_display.update(self._fmt_time(self.decay))
        self._mark_dirty()
        self._autosave_state()

    def action_adjust_sustain(self, direction: str = "up"):
        self.sustain = min(1.0, self.sustain + 0.05) if direction == "up" else max(0.0, self.sustain - 0.05)
        self.synth_engine.update_parameters(sustain=self.sustain)
        if self.sustain_display:
            self.sustain_display.update(
                self._fmt_slider(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%")
            )
        self._mark_dirty()
        self._autosave_state()

    def action_adjust_release(self, direction: str = "up"):
        self.release = min(5.0, self.release * 1.15) if direction == "up" else max(0.001, self.release / 1.15)
        self.synth_engine.update_parameters(release=self.release)
        if self.release_display:
            self.release_display.update(self._fmt_time(self.release))
        self._mark_dirty()
        self._autosave_state()

    def action_adjust_intensity(self, direction: str = "up"):
        self.intensity = min(1.0, self.intensity + 0.05) if direction == "up" else max(0.0, self.intensity - 0.05)
        self.synth_engine.update_parameters(intensity=self.intensity)
        if self.intensity_display:
            self.intensity_display.update(
                self._fmt_slider(self.intensity, 0.0, 1.0, f"{int(self.intensity * 100)}%")
            )
        self._mark_dirty()
        self._autosave_state()

    def action_panic(self):
        self.synth_engine.all_notes_off()
        self.app.notify("🛑 All notes off (Panic)", severity="warning", timeout=2)

    def action_randomize(self):
        """Roll the dice — generate musically useful random synth parameters."""

        # Waveform — equal chance across all four
        self.waveform = random.choice(["sine", "square", "sawtooth", "triangle"])

        # Octave — weighted towards centre (8') for playability
        self.octave = random.choices([-2, -1, 0, 1, 2], weights=[1, 2, 4, 2, 1])[0]

        # Amp — stay in a reasonable range (50–95%)
        self.amp_level = round(random.uniform(0.50, 0.95), 2)

        # Filter — log-distributed so low values aren't under-represented
        # musical range: dark (200 Hz) → bright (18 kHz)
        self.cutoff = round(10 ** random.uniform(math.log10(200), math.log10(18000)), 1)

        # Resonance — mostly subtle, occasionally spiky
        self.resonance = round(random.choices(
            [random.uniform(0.0, 0.3),   # subtle
             random.uniform(0.3, 0.65),  # moderate
             random.uniform(0.65, 0.9)], # resonant
            weights=[50, 35, 15]
        )[0], 2)

        # Attack — log-distributed: mostly fast, some slow pads
        self.attack = round(10 ** random.uniform(math.log10(0.001), math.log10(2.0)), 4)

        # Decay — log-distributed: 1 ms → 2 s
        self.decay = round(10 ** random.uniform(math.log10(0.001), math.log10(2.0)), 4)

        # Sustain — full range, slightly weighted towards held notes
        self.sustain = round(random.choices(
            [random.uniform(0.0, 0.3),   # percussive / plucky
             random.uniform(0.3, 0.7),   # expressive
             random.uniform(0.7, 1.0)],  # pad / organ
            weights=[25, 35, 40]
        )[0], 2)

        # Release — log-distributed: 10 ms → 3 s
        self.release = round(10 ** random.uniform(math.log10(0.01), math.log10(3.0)), 4)

        # Intensity — keep it audible (40–100%)
        self.intensity = round(random.uniform(0.40, 1.0), 2)

        self._push_params_to_engine()
        self._refresh_all_displays()
        self._mark_dirty()
        self._autosave_state()
        self.app.notify("🎲 Randomized!", timeout=2)

    # ── Display refresh ──────────────────────────────────────────

    def _refresh_all_displays(self):
        if self.waveform_display:
            self.waveform_display.update(self._fmt_waveform())
        if self.octave_display:
            self.octave_display.update(self._fmt_octave())
        if self.cutoff_display:
            self.cutoff_display.update(self._fmt_cutoff())
        if self.resonance_display:
            self.resonance_display.update(self._fmt_resonance())
        if self.attack_display:
            self.attack_display.update(self._fmt_time(self.attack))
        if self.decay_display:
            self.decay_display.update(self._fmt_time(self.decay))
        if self.sustain_display:
            self.sustain_display.update(
                self._fmt_slider(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%")
            )
        if self.release_display:
            self.release_display.update(self._fmt_time(self.release))
        if self.intensity_display:
            self.intensity_display.update(
                self._fmt_slider(self.intensity, 0.0, 1.0, f"{int(self.intensity * 100)}%")
            )
        if self.amp_display:
            self.amp_display.update(
                self._fmt_slider(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%")
            )

    # ── Box drawing helpers ──────────────────────────────────────

    def _section_top(self, title: str, width: int = 28) -> str:
        title_padded = f" {title} "
        padding = width - len(title_padded) - 2
        lp = padding // 2
        rp = padding - lp
        return f"[bold #00ff00]╔{'─' * lp}{title_padded}{'─' * rp}╗[/]"

    def _section_bottom(self, width: int = 28) -> str:
        return f"[bold #00ff00]╚{'─' * (width - 2)}╝[/]"

    def _box_line(self, content: str, width: int = 28) -> str:
        content = content.replace("│", "").strip()
        inner = width - 2
        if len(content) > inner:
            content = content[:inner]
        pad = inner - len(content)
        lp = pad // 2
        rp = pad - lp
        return f"[#00ff00]│{' ' * lp}{content}{' ' * rp}│[/]"

    def _empty_line(self, width: int = 28) -> str:
        return f"[#00ff00]│{' ' * (width - 2)}│[/]"

    def _slider(self, value: float, min_val: float, max_val: float, width: int = 26) -> str:
        norm = (value - min_val) / (max_val - min_val)
        filled = int(norm * width)
        empty = width - filled
        if filled > 0 and empty > 0:
            return "[#00ff00]" + "█" * filled + "[/][#333333]" + "░" * empty + "[/]"
        elif filled == width:
            return "[#00ff00]" + "█" * filled + "[/]"
        return "[#333333]" + "░" * empty + "[/]"

    def _fmt_slider(self, value: float, min_val: float, max_val: float, label: str) -> str:
        bar = self._slider(value, min_val, max_val)
        total = 26
        pad = total - len(label)
        lp = pad // 2
        rp = pad - lp
        val_padded = " " * lp + label + " " * rp
        return f"[#00ff00]│{bar}│[/]\n[#00ff00]│{val_padded}│[/]"

    def _fmt_time(self, t: float) -> str:
        log_t = math.log10(t)
        log_min = math.log10(0.001)
        log_max = math.log10(5.0)
        norm = (log_t - log_min) / (log_max - log_min)
        label = f"{t * 1000:.0f}ms" if t < 0.01 else f"{t:.2f}s"
        bar = self._slider(norm, 0.0, 1.0)
        total = 26
        pad = total - len(label)
        lp = pad // 2
        rp = pad - lp
        val_padded = " " * lp + label + " " * rp
        return f"[#00ff00]│{bar}│[/]\n[#00ff00]│{val_padded}│[/]"

    def _fmt_cutoff(self) -> str:
        log_c = math.log10(self.cutoff)
        log_min = math.log10(20.0)
        log_max = math.log10(20000.0)
        norm = (log_c - log_min) / (log_max - log_min)
        label = f"{self.cutoff / 1000:.3f} kHz" if self.cutoff >= 1000 else f"{self.cutoff:.3f} Hz"
        return self._fmt_slider(norm, 0.0, 1.0, label)

    def _fmt_resonance(self) -> str:
        return self._fmt_slider(self.resonance / 0.9, 0.0, 1.0, f"{int(self.resonance * 100)}%")

    def _fmt_waveform(self) -> str:
        labels = {"sine": "SIN", "square": "SQR", "sawtooth": "SAW", "triangle": "TRI"}
        parts = []
        for key, tag in labels.items():
            if self.waveform == key:
                parts.append(f"[bold reverse]{tag}[/]")
            else:
                parts.append(tag)
        line = "  ".join(parts)
        plain = re.sub(r'\[.*?\]', '', line)
        total = 26
        pad = total - len(plain)
        lp = pad // 2
        rp = pad - lp
        return f"[#00ff00]│{' ' * lp}{line}{' ' * rp}│[/]"

    def _fmt_octave(self) -> str:
        feet = {-2: "32'", -1: "16'", 0: "8'", 1: "4'", 2: "2'"}
        dots = " ".join("●" if p == self.octave else "○" for p in [-2, -1, 0, 1, 2])
        label = f"{feet.get(self.octave, '8')} ({self.octave:+d})"
        total = 26
        lines = []
        for text in [dots, label]:
            pad = total - len(text)
            lp = pad // 2
            rp = pad - lp
            lines.append(f"[#00ff00]│{' ' * lp}{text}{' ' * rp}│[/]")
        return "\n".join(lines)
