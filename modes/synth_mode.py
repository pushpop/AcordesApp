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


# ── Section navigation grid ───────────────────────────────────────────────────
# Sections arranged in visual order: row × col.
# Arrow keys move within this grid; wrapping is per-axis.
_SECTION_GRID = [
    ["oscillator", "filter",  "envelope", "lfo"   ],   # row 0
    ["chorus",     "fx",      "arpeggio", "mixer"  ],   # row 1
]
_FLAT_SECTIONS = [s for row in _SECTION_GRID for s in row]  # linear order


class SynthMode(Widget):
    """Widget for polyphonic synthesizer interface with preset management."""

    can_focus = True

    BINDINGS = [
        # ── Preset navigation (only active when no section is focused) ──────
        Binding("left",  "nav_left",   "◄ / Preset prev", show=False),
        Binding("right", "nav_right",  "► / Preset next", show=False),
        Binding("up",    "nav_up",     "▲ / Vol+",        show=False),
        Binding("down",  "nav_down",   "▼ / Vol-",        show=False),
        Binding("escape","nav_escape", "Unfocus",          show=False),
        Binding("enter", "nav_enter", "Enter/exit focus", show=False),
        Binding("comma",  "preset_prev",           "Preset ◄",        show=False),
        Binding("full_stop", "preset_next",         "Preset ►",        show=False),
        Binding("ctrl+n", "save_preset_new",      "Save New Preset", show=False),
        Binding("ctrl+s", "save_preset_overwrite","Update Preset",  show=False),
        # ── Alt+Arrow — adjust focused parameter ──────────────────────────
        Binding("alt+left",  "adjust_focused('down')", "Focused param -", show=False),
        Binding("alt+right", "adjust_focused('up')",   "Focused param +", show=False),
        # ── Focus-mode value keys ──────────────────────────────────────────
        # Q/W = increment/decrement the focused parameter
        Binding("q", "param_down", "Param-", show=False),
        Binding("w", "param_up",   "Param+", show=False),
        # ── Legacy global shortcuts (active only when no section focused) ──
        # w is reserved for param_down in focus mode; octave uses Q/W in legacy via param_up/down
        Binding("s", "adjust_octave('down')",      "Oct-",   show=False),
        Binding("e", "adjust_cutoff('up')",        "Cut+",   show=False),
        Binding("d", "adjust_cutoff('down')",      "Cut-",   show=False),
        Binding("r", "adjust_resonance('up')",     "Res+",   show=False),
        Binding("f", "adjust_resonance('down')",   "Res-",   show=False),
        Binding("t", "adjust_attack('up')",        "Atk+",   show=False),
        Binding("g", "adjust_attack('down')",      "Atk-",   show=False),
        Binding("y", "adjust_decay('up')",         "Dec+",   show=False),
        Binding("h", "adjust_decay('down')",       "Dec-",   show=False),
        Binding("u", "adjust_sustain('up')",       "Sus+",   show=False),
        Binding("j", "adjust_sustain('down')",     "Sus-",   show=False),
        Binding("i", "adjust_release('up')",       "Rel+",   show=False),
        Binding("k", "adjust_release('down')",     "Rel-",   show=False),
        Binding("o", "adjust_intensity('up')",     "Int+",   show=False),
        Binding("l", "adjust_intensity('down')",   "Int-",   show=False),
        Binding("left_square_bracket",  "adjust_master_volume('down')", "MVol-", show=False),
        Binding("right_square_bracket", "adjust_master_volume('up')",   "MVol+", show=False),
        # ── Global ────────────────────────────────────────────────────────
        Binding("space", "panic",     "Panic (All Notes Off)", show=False),
        Binding("minus", "randomize", "🎲 Randomize",          show=False),
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

    #synth-grid {
        layout: vertical;
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }

    #synth-container {
        layout: horizontal;
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }

    #synth-container-bottom {
        layout: horizontal;
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }

    #preset-bar {
        width: 100%;
        height: 1;
        background: #0a120a;
        color: #00ff00;
        padding: 0 1;
        margin: 0;
    }

    #controls-help {
        width: 100%;
        height: 1;
        background: #111111;
        border-top: solid #1a3a1a;
        padding: 0 1;
        margin: 0;
    }

    #oscillator-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }

    #filter-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }

    #envelope-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }

    #mixer-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }

    #lfo-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }

    #chorus-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }

    #arpeggio-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }

    #fx-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #0d0d0d;
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
        color: #556655;
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

    # ── Section parameter definitions ─────────────────────────────────────────
    # Each entry: (display_name, n_params)
    # n_params tells nav_up/down how many steps before wrapping.
    _SECTION_PARAMS = {
        "oscillator": ["Wave", "Octave"],
        "filter":     ["Cutoff", "Resonance"],
        "envelope":   ["Attack", "Decay", "Sustain", "Release", "Intensity"],
        "lfo":        ["Rate", "Depth", "Shape", "Target"],
        "chorus":     ["Rate", "Depth", "Mix", "Voices"],
        "fx":         ["Reverb Size", "Reverb Mix", "Delay Time", "Delay Fdbk"],
        "arpeggio":   ["Mode", "Rate", "Gate", "Range"],
        "mixer":      ["Amp", "Master Vol"],
    }

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

        # GLOBAL MASTER VOLUME (Persisted but not in presets)
        self.master_volume = self.config_manager.get_synth_state().get("master_volume", 1.0)

        # ── Focus state ──────────────────────────────────────────────────────
        # _focus_section: which section is currently focused (None = global mode)
        # _focus_param:   index into _SECTION_PARAMS[section] for the active param
        self._focus_section: Optional[str] = None
        self._focus_param: int = 0

        # Widget references for live updates
        self.waveform_display       = None
        self.waveform_shape_display = None
        self.octave_display         = None
        self.amp_display            = None
        self.master_volume_display  = None
        self.cutoff_display         = None
        self.resonance_display      = None
        self.attack_display         = None
        self.decay_display          = None
        self.sustain_display        = None
        self.release_display        = None
        self.intensity_display      = None
        self.header                 = None
        self.controls_help          = None
        self.current_note: Optional[int] = None

        # IDs of the section-header Labels, keyed by section name.
        # Populated in compose(); used to re-render the header on focus change.
        self._section_header_ids: dict = {}

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

        # ── PRESET BAR ───────────────────────────────────────────────
        yield Static(self._fmt_preset_bar(), id="preset-bar")

        with Vertical(id="synth-grid"):
            # ── ROW 1: OSCILLATOR · FILTER · ENVELOPE · LFO ─────────────
            with Horizontal(id="synth-container"):
                # ── OSCILLATOR ───────────────────────────────────────────
                with Vertical(id="oscillator-section"):
                    hdr = Label(self._section_top("OSCILLATOR", False), classes="section-label", id="hdr-oscillator")
                    self._section_header_ids["oscillator"] = "hdr-oscillator"
                    yield hdr
                    yield Label(self._row_label("Wave", ""), classes="control-label", id="lbl-oscillator-0")
                    self.waveform_display = Label(self._fmt_waveform(), classes="control-value", id="waveform-display")
                    yield self.waveform_display
                    yield Label(self._row_label("Shape", ""), classes="control-label")
                    self.waveform_shape_display = Label(self._fmt_waveform_shape(), classes="control-value", id="waveform-shape-display")
                    yield self.waveform_shape_display
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Octave", ""), classes="control-label", id="lbl-oscillator-1")
                    self.octave_display = Label(self._fmt_octave(), classes="control-value", id="octave-display")
                    yield self.octave_display
                    yield Label(self._section_bottom(), classes="section-label")

                # ── FILTER ───────────────────────────────────────────────
                with Vertical(id="filter-section"):
                    hdr = Label(self._section_top("FILTER", False), classes="section-label", id="hdr-filter")
                    self._section_header_ids["filter"] = "hdr-filter"
                    yield hdr
                    yield Label(self._row_label("Cutoff", ""), classes="control-label", id="lbl-filter-0")
                    self.cutoff_display = Label(self._fmt_cutoff(), classes="control-value", id="cutoff-display")
                    yield self.cutoff_display
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Resonance", ""), classes="control-label", id="lbl-filter-1")
                    self.resonance_display = Label(self._fmt_resonance(), classes="control-value", id="resonance-display")
                    yield self.resonance_display
                    yield Label(self._section_bottom(), classes="section-label")

                # ── ENVELOPE ─────────────────────────────────────────────
                with Vertical(id="envelope-section"):
                    hdr = Label(self._section_top("ENVELOPE", False), classes="section-label", id="hdr-envelope")
                    self._section_header_ids["envelope"] = "hdr-envelope"
                    yield hdr
                    yield Label(self._row_label("Attack", ""), classes="control-label", id="lbl-envelope-0")
                    self.attack_display = Label(self._fmt_time(self.attack), classes="control-value", id="attack-display")
                    yield self.attack_display
                    yield Label(self._row_label("Decay", ""), classes="control-label", id="lbl-envelope-1")
                    self.decay_display = Label(self._fmt_time(self.decay), classes="control-value", id="decay-display")
                    yield self.decay_display
                    yield Label(self._row_label("Sustain", ""), classes="control-label", id="lbl-envelope-2")
                    self.sustain_display = Label(
                        self._fmt_knob(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"),
                        classes="control-value", id="sustain-display")
                    yield self.sustain_display
                    yield Label(self._row_label("Release", ""), classes="control-label", id="lbl-envelope-3")
                    self.release_display = Label(self._fmt_time(self.release), classes="control-value", id="release-display")
                    yield self.release_display
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Intensity", ""), classes="control-label", id="lbl-envelope-4")
                    self.intensity_display = Label(
                        self._fmt_knob(self.intensity, 0.0, 1.0, f"{int(self.intensity * 100)}%"),
                        classes="control-value", id="intensity-display")
                    yield self.intensity_display
                    yield Label(self._section_bottom(), classes="section-label")

                # ── LFO ──────────────────────────────────────────────────
                with Vertical(id="lfo-section"):
                    hdr = Label(self._section_top("LFO", False), classes="section-label", id="hdr-lfo")
                    self._section_header_ids["lfo"] = "hdr-lfo"
                    yield hdr
                    yield Label(self._row_label("Rate", ""), classes="control-label", id="lbl-lfo-0")
                    yield Label(self._fmt_knob(0.2, 0.0, 1.0, "0.20 Hz"), classes="control-value")
                    yield Label(self._row_label("Depth", ""), classes="control-label", id="lbl-lfo-1")
                    yield Label(self._fmt_knob(0.0, 0.0, 1.0, "0%"), classes="control-value")
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Shape", ""), classes="control-label", id="lbl-lfo-2")
                    yield Label(self._fmt_dummy_selector(["SIN", "TRI", "S&H", "SQR"], 0), classes="control-value")
                    yield Label(self._row_label("Target", ""), classes="control-label", id="lbl-lfo-3")
                    yield Label(self._fmt_dummy_selector(["VCO", "VCF", "VCA"], 1), classes="control-value")
                    yield Label(self._section_bottom(), classes="section-label")

            # ── ROW 2: CHORUS · FX · ARPEGGIO · MIXER ───────────────────
            with Horizontal(id="synth-container-bottom"):

                # ── CHORUS ───────────────────────────────────────────────
                with Vertical(id="chorus-section"):
                    hdr = Label(self._section_top("CHORUS", False), classes="section-label", id="hdr-chorus")
                    self._section_header_ids["chorus"] = "hdr-chorus"
                    yield hdr
                    yield Label(self._row_label("Rate", ""), classes="control-label", id="lbl-chorus-0")
                    yield Label(self._fmt_knob(0.3, 0.0, 1.0, "0.30 Hz"), classes="control-value")
                    yield Label(self._row_label("Depth", ""), classes="control-label", id="lbl-chorus-1")
                    yield Label(self._fmt_knob(0.0, 0.0, 1.0, "0%"), classes="control-value")
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Mix", ""), classes="control-label", id="lbl-chorus-2")
                    yield Label(self._fmt_knob(0.0, 0.0, 1.0, "0%"), classes="control-value")
                    yield Label(self._row_label("Voices", ""), classes="control-label", id="lbl-chorus-3")
                    yield Label(self._fmt_dummy_selector(["1", "2", "3", "4"], 2), classes="control-value")
                    yield Label(self._section_bottom(), classes="section-label")

                # ── FX ───────────────────────────────────────────────────
                with Vertical(id="fx-section"):
                    hdr = Label(self._section_top("FX", False), classes="section-label", id="hdr-fx")
                    self._section_header_ids["fx"] = "hdr-fx"
                    yield hdr
                    yield Label(self._row_label("Reverb Size", ""), classes="control-label", id="lbl-fx-0")
                    yield Label(self._fmt_knob(0.0, 0.0, 1.0, "0%"), classes="control-value")
                    yield Label(self._row_label("Reverb Mix", ""), classes="control-label", id="lbl-fx-1")
                    yield Label(self._fmt_knob(0.0, 0.0, 1.0, "0%"), classes="control-value")
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Delay Time", ""), classes="control-label", id="lbl-fx-2")
                    yield Label(self._fmt_knob(0.0, 0.0, 1.0, "250ms"), classes="control-value")
                    yield Label(self._row_label("Delay Fdbk", ""), classes="control-label", id="lbl-fx-3")
                    yield Label(self._fmt_knob(0.0, 0.0, 1.0, "0%"), classes="control-value")
                    yield Label(self._section_bottom(), classes="section-label")

                # ── ARPEGGIO ─────────────────────────────────────────────
                with Vertical(id="arpeggio-section"):
                    hdr = Label(self._section_top("ARPEGGIO", False), classes="section-label", id="hdr-arpeggio")
                    self._section_header_ids["arpeggio"] = "hdr-arpeggio"
                    yield hdr
                    yield Label(self._row_label("Mode", ""), classes="control-label", id="lbl-arpeggio-0")
                    yield Label(self._fmt_dummy_selector(["UP", "DN", "U+D", "RND"], 0), classes="control-value")
                    yield Label(self._row_label("Rate", ""), classes="control-label", id="lbl-arpeggio-1")
                    yield Label(self._fmt_knob(0.5, 0.0, 1.0, "120 BPM"), classes="control-value")
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Gate", ""), classes="control-label", id="lbl-arpeggio-2")
                    yield Label(self._fmt_knob(0.5, 0.0, 1.0, "50%"), classes="control-value")
                    yield Label(self._row_label("Range", ""), classes="control-label", id="lbl-arpeggio-3")
                    yield Label(self._fmt_dummy_selector(["1", "2", "3", "4"], 1), classes="control-value")
                    yield Label(self._section_bottom(), classes="section-label")

                # ── MIXER ────────────────────────────────────────────────
                with Vertical(id="mixer-section"):
                    hdr = Label(self._section_top("MIXER", False), classes="section-label", id="hdr-mixer")
                    self._section_header_ids["mixer"] = "hdr-mixer"
                    yield hdr
                    yield Label(self._row_label("Amp", ""), classes="control-label", id="lbl-mixer-0")
                    self.amp_display = Label(
                        self._fmt_knob(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%"),
                        classes="control-value", id="amp-display")
                    yield self.amp_display
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Master Vol", ""), classes="control-label", id="lbl-mixer-1")
                    self.master_volume_display = Label(
                        self._fmt_knob(self.master_volume, 0.0, 1.0, f"{int(self.master_volume * 100)}%"),
                        classes="control-value", id="master-volume-display")
                    yield self.master_volume_display
                    yield Label(self._section_bottom(), classes="section-label")

        # ── CONTROLS HELP ────────────────────────────────────────────
        self.controls_help = Static(self._fmt_help_bar(), id="controls-help")
        yield self.controls_help

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

    def _on_note_off(self, note: int, velocity: int = 0):
        self.synth_engine.note_off(note, velocity)
        if self.current_note == note:
            self.current_note = None
            self._update_preset_ui()

    def _on_pitch_bend(self, value: int):
        self.synth_engine.pitch_bend_change(value)

    def _on_control_change(self, controller: int, value: int):
        if controller == 1:
            self.synth_engine.modulation_change(value)

    # ── Focus / navigation ────────────────────────────────────────

    def _focused(self) -> bool:
        return self._focus_section is not None

    def _set_focus(self, section: Optional[str], param: int = 0):
        old_sec = self._focus_section
        self._focus_section = section
        # Clamp param index to valid range for the new section
        if section is not None:
            n = len(self._SECTION_PARAMS.get(section, []))
            param = min(param, n - 1) if n > 0 else 0
        self._focus_param   = param
        # Redraw affected section headers
        for sec in set(filter(None, [old_sec, section])):
            self._redraw_section_header(sec)
        # Redraw param labels for old and new sections
        if old_sec:
            self._redraw_param_labels(old_sec)
        if section:
            self._redraw_param_labels(section)
        self._redraw_help_bar()

    def _redraw_section_header(self, section: str):
        wid_id = self._section_header_ids.get(section)
        if not wid_id:
            return
        try:
            lbl = self.query_one(f"#{wid_id}", Label)
            title = section.upper()
            lbl.update(self._section_top(title, self._focus_section == section))
        except Exception:
            pass

    def _redraw_param_labels(self, section: str):
        """Re-render every param-row label in section with focus highlight."""
        params = self._SECTION_PARAMS.get(section, [])
        for idx, name in enumerate(params):
            wid_id = f"lbl-{section}-{idx}"
            try:
                lbl = self.query_one(f"#{wid_id}", Label)
                active = (self._focus_section == section and self._focus_param == idx)
                lbl.update(self._row_label(name, "", active=active))
            except Exception:
                pass

    def _redraw_help_bar(self):
        if self.controls_help:
            self.controls_help.update(self._fmt_help_bar())

    def _grid_pos(self, section: str) -> tuple[int, int]:
        for r, row in enumerate(_SECTION_GRID):
            if section in row:
                return r, row.index(section)
        return 0, 0

    def action_nav_left(self):
        if not self._focused():
            self.action_preset_prev()
            return
        r, c = self._grid_pos(self._focus_section)
        nc = (c - 1) % len(_SECTION_GRID[r])
        self._set_focus(_SECTION_GRID[r][nc], self._focus_param)

    def action_nav_right(self):
        if not self._focused():
            self.action_preset_next()
            return
        r, c = self._grid_pos(self._focus_section)
        nc = (c + 1) % len(_SECTION_GRID[r])
        self._set_focus(_SECTION_GRID[r][nc], self._focus_param)

    def action_nav_up(self):
        if not self._focused():
            self.action_adjust_volume("up")
            return
        params = self._SECTION_PARAMS.get(self._focus_section, [])
        if not params:
            return
        if self._focus_param > 0:
            # Move up within section
            self._set_focus(self._focus_section, self._focus_param - 1)
        else:
            # At top of section — jump to row above (same column), last param
            r, c = self._grid_pos(self._focus_section)
            nr = (r - 1) % len(_SECTION_GRID)
            new_sec = _SECTION_GRID[nr][c]
            new_params = self._SECTION_PARAMS.get(new_sec, [])
            self._set_focus(new_sec, max(0, len(new_params) - 1))

    def action_nav_down(self):
        if not self._focused():
            self.action_adjust_volume("down")
            return
        params = self._SECTION_PARAMS.get(self._focus_section, [])
        if not params:
            return
        if self._focus_param < len(params) - 1:
            # Move down within section
            self._set_focus(self._focus_section, self._focus_param + 1)
        else:
            # At bottom of section — jump to row below (same column), first param
            r, c = self._grid_pos(self._focus_section)
            nr = (r + 1) % len(_SECTION_GRID)
            new_sec = _SECTION_GRID[nr][c]
            self._set_focus(new_sec, 0)

    def action_nav_escape(self):
        if self._focused():
            self._set_focus(None)
        else:
            self.screen.action_quit_app()

    def action_nav_enter(self):
        """Enter focus on the first section / exit focus if already in it."""
        if self._focused():
            self._set_focus(None)
        else:
            self._set_focus(_SECTION_GRID[0][0], 0)

    # ── Q / A  →  param_up / param_down ──────────────────────────

    def action_adjust_focused(self, direction: str = "up"):
        """Alt+Left/Right — adjust the currently focused parameter."""
        if self._focused():
            self._adjust_focused_param(direction)

    def action_param_up(self):
        if self._focused():
            self._adjust_focused_param("up")
        else:
            self._do_adjust_octave("up")

    def action_param_down(self):
        if self._focused():
            self._adjust_focused_param("down")
        else:
            self._do_adjust_octave("down")

    def _adjust_focused_param(self, direction: str):
        """Dispatch to the correct adjustment action for the focused param.
        Calls _do_* helpers that bypass the focus guard on action methods."""
        sec   = self._focus_section
        pidx  = self._focus_param
        params = self._SECTION_PARAMS.get(sec, [])
        if not params or pidx >= len(params):
            return
        name = params[pidx]

        # OSC
        if sec == "oscillator":
            if name == "Wave":
                self._do_toggle_waveform("forward" if direction == "up" else "backward")
            elif name == "Octave":
                self._do_adjust_octave(direction)
        # FILTER
        elif sec == "filter":
            if name == "Cutoff":      self._do_adjust_cutoff(direction)
            elif name == "Resonance": self._do_adjust_resonance(direction)
        # ENVELOPE
        elif sec == "envelope":
            if name == "Attack":      self._do_adjust_attack(direction)
            elif name == "Decay":     self._do_adjust_decay(direction)
            elif name == "Sustain":   self._do_adjust_sustain(direction)
            elif name == "Release":   self._do_adjust_release(direction)
            elif name == "Intensity": self._do_adjust_intensity(direction)
        # MIXER
        elif sec == "mixer":
            if name == "Amp":          self._do_adjust_volume(direction)
            elif name == "Master Vol": self._do_adjust_master_volume(direction)
        # Dummy sections — not yet wired, silently ignore

    # ── Core param mutators (no focus guard — used by focus dispatch) ─────────

    def _do_toggle_waveform(self, way: str = "forward"):
        order = ["pure_sine", "sine", "square", "sawtooth", "triangle"]
        delta = 1 if way == "forward" else -1
        self.waveform = order[(order.index(self.waveform) + delta) % len(order)]
        self.synth_engine.update_parameters(waveform=self.waveform)
        if self.waveform_display:
            self.waveform_display.update(self._fmt_waveform())
        if self.waveform_shape_display:
            self.waveform_shape_display.update(self._fmt_waveform_shape())
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_octave(self, direction: str = "up"):
        self.octave = min(2, self.octave + 1) if direction == "up" else max(-2, self.octave - 1)
        self.synth_engine.update_parameters(octave=self.octave)
        if self.octave_display:
            self.octave_display.update(self._fmt_octave())
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_volume(self, direction: str = "up"):
        self.amp_level = min(1.0, self.amp_level + 0.05) if direction == "up" else max(0.0, self.amp_level - 0.05)
        self.synth_engine.update_parameters(amp_level=self.amp_level)
        if self.amp_display:
            self.amp_display.update(self._fmt_knob(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%"))
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_master_volume(self, direction: str = "up"):
        self.master_volume = min(1.0, self.master_volume + 0.05) if direction == "up" else max(0.0, self.master_volume - 0.05)
        self.synth_engine.update_parameters(master_volume=self.master_volume)
        if self.master_volume_display:
            self.master_volume_display.update(self._fmt_knob(self.master_volume, 0.0, 1.0, f"{int(self.master_volume * 100)}%"))
        self._autosave_state()

    def _do_adjust_cutoff(self, direction: str = "up"):
        self.cutoff = min(20000.0, self.cutoff * 1.1) if direction == "up" else max(20.0, self.cutoff / 1.1)
        self.synth_engine.update_parameters(cutoff=self.cutoff)
        if self.cutoff_display:
            self.cutoff_display.update(self._fmt_cutoff())
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_resonance(self, direction: str = "up"):
        self.resonance = min(0.9, self.resonance + 0.05) if direction == "up" else max(0.0, self.resonance - 0.05)
        self.synth_engine.update_parameters(resonance=self.resonance)
        if self.resonance_display:
            self.resonance_display.update(self._fmt_resonance())
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_attack(self, direction: str = "up"):
        self.attack = min(5.0, self.attack * 1.15) if direction == "up" else max(0.001, self.attack / 1.15)
        self.synth_engine.update_parameters(attack=self.attack)
        if self.attack_display:
            self.attack_display.update(self._fmt_time(self.attack))
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_decay(self, direction: str = "up"):
        self.decay = min(5.0, self.decay * 1.15) if direction == "up" else max(0.001, self.decay / 1.15)
        self.synth_engine.update_parameters(decay=self.decay)
        if self.decay_display:
            self.decay_display.update(self._fmt_time(self.decay))
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_sustain(self, direction: str = "up"):
        self.sustain = min(1.0, self.sustain + 0.05) if direction == "up" else max(0.0, self.sustain - 0.05)
        self.synth_engine.update_parameters(sustain=self.sustain)
        if self.sustain_display:
            self.sustain_display.update(self._fmt_knob(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"))
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_release(self, direction: str = "up"):
        self.release = min(5.0, self.release * 1.15) if direction == "up" else max(0.001, self.release / 1.15)
        self.synth_engine.update_parameters(release=self.release)
        if self.release_display:
            self.release_display.update(self._fmt_time(self.release))
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_intensity(self, direction: str = "up"):
        self.intensity = min(1.0, self.intensity + 0.05) if direction == "up" else max(0.0, self.intensity - 0.05)
        self.synth_engine.update_parameters(intensity=self.intensity)
        if self.intensity_display:
            self.intensity_display.update(self._fmt_knob(self.intensity, 0.0, 1.0, f"{int(self.intensity * 100)}%"))
        self._mark_dirty()
        self._autosave_state()

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
        params.pop("master_volume", None)
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
                "⚠ No preset loaded — use Ctrl+N to save a new one",
                severity="warning", timeout=3
            )
            return
        params = self._current_params()
        params.pop("master_volume", None)
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
            master_volume=self.master_volume,
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
            "waveform":      self.waveform,
            "octave":        self.octave,
            "amp_level":     self.amp_level,
            "master_volume": self.master_volume,
            "cutoff":        self.cutoff,
            "resonance":     self.resonance,
            "attack":        self.attack,
            "decay":         self.decay,
            "sustain":       self.sustain,
            "release":       self.release,
            "intensity":     self.intensity,
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

    def _update_preset_ui(self):
        try:
            bar = self.query_one("#preset-bar", Static)
            bar.update(self._fmt_preset_bar())
        except Exception:
            pass

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

    # ── Keyboard actions (legacy global shortcuts) ────────────────

    def action_toggle_waveform_forward(self):
        if self._focused():
            return
        self._do_toggle_waveform("forward")

    def action_toggle_waveform_backward(self):
        if self._focused():
            return
        self._do_toggle_waveform("backward")

    def action_adjust_octave(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_octave(direction)

    def action_adjust_volume(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_volume(direction)

    def action_adjust_master_volume(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_master_volume(direction)

    def action_adjust_cutoff(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_cutoff(direction)

    def action_adjust_resonance(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_resonance(direction)

    def action_adjust_attack(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_attack(direction)

    def action_adjust_decay(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_decay(direction)

    def action_adjust_sustain(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_sustain(direction)

    def action_adjust_release(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_release(direction)

    def action_adjust_intensity(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_intensity(direction)

    def action_panic(self):
        self.synth_engine.all_notes_off()
        self.app.notify("🛑 All notes off (Panic)", severity="warning", timeout=2)

    def action_randomize(self):
        """Roll the dice — generate musically useful random synth parameters."""
        self.waveform = random.choice(["pure_sine", "sine", "square", "sawtooth", "triangle"])
        self.octave = random.choices([-2, -1, 0, 1, 2], weights=[1, 2, 4, 2, 1])[0]
        self.amp_level = round(random.uniform(0.50, 0.95), 2)
        self.cutoff = round(10 ** random.uniform(math.log10(200), math.log10(18000)), 1)
        self.resonance = round(random.choices(
            [random.uniform(0.0, 0.3), random.uniform(0.3, 0.65), random.uniform(0.65, 0.9)],
            weights=[50, 35, 15]
        )[0], 2)
        self.attack = round(10 ** random.uniform(math.log10(0.001), math.log10(2.0)), 4)
        self.decay = round(10 ** random.uniform(math.log10(0.001), math.log10(2.0)), 4)
        self.sustain = round(random.choices(
            [random.uniform(0.0, 0.3), random.uniform(0.3, 0.7), random.uniform(0.7, 1.0)],
            weights=[25, 35, 40]
        )[0], 2)
        self.release = round(10 ** random.uniform(math.log10(0.01), math.log10(3.0)), 4)
        self.intensity = round(random.uniform(0.40, 1.0), 2)

        self._push_params_to_engine()
        self._refresh_all_displays()
        self._mark_dirty()
        self._autosave_state()
        self.app.notify("🎲 Randomized!", timeout=2)

    # ── Display refresh ──────────────────────────────────────────

    def _refresh_all_displays(self):
        if self.waveform_display: self.waveform_display.update(self._fmt_waveform())
        if self.waveform_shape_display: self.waveform_shape_display.update(self._fmt_waveform_shape())
        if self.octave_display: self.octave_display.update(self._fmt_octave())
        if self.cutoff_display: self.cutoff_display.update(self._fmt_cutoff())
        if self.resonance_display: self.resonance_display.update(self._fmt_resonance())
        if self.attack_display: self.attack_display.update(self._fmt_time(self.attack))
        if self.decay_display: self.decay_display.update(self._fmt_time(self.decay))
        if self.sustain_display: self.sustain_display.update(self._fmt_knob(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"))
        if self.release_display: self.release_display.update(self._fmt_time(self.release))
        if self.intensity_display: self.intensity_display.update(self._fmt_knob(self.intensity, 0.0, 1.0, f"{int(self.intensity * 100)}%"))
        if self.amp_display: self.amp_display.update(self._fmt_knob(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%"))
        if self.master_volume_display: self.master_volume_display.update(self._fmt_knob(self.master_volume, 0.0, 1.0, f"{int(self.master_volume * 100)}%"))

    # ── Rendering helpers ────────────────────────────────────────

    # Inner width of a section column (characters between the border chars).
    _W = 26

    def _section_top(self, title: str, focused: bool = False) -> str:
        """Rounded-corner section header. Cyan + ◈ marker when focused."""
        inner = self._W
        marker = " ◈" if focused else ""
        title_padded = f" {title}{marker} "
        dashes = max(0, inner - len(title_padded))
        lp = dashes // 2
        rp = dashes - lp
        color = "#00ffff" if focused else "#00cc00"
        return f"[bold {color}]╭{'─' * lp}{title_padded}{'─' * rp}╮[/]"

    def _section_bottom(self) -> str:
        """Rounded-corner section footer: ╰────────────╯"""
        return f"[bold #00cc00]╰{'─' * self._W}╯[/]"

    def _row_label(self, name: str, key: str, active: bool = False) -> str:
        """Row label. When active=True the name glows bright cyan (focused param)."""
        inner = self._W
        key_str = f" {key}" if key else ""
        left  = f" {name}"
        right = f"{key_str} "
        gap   = max(0, inner - len(left) - len(right))
        line  = left + " " * gap + right
        if active:
            return f"[#00ffff]│[bold #00ffff]{line}│[/]"
        return f"[#00cc00]│[/][#445544]{line}[/][#00cc00]│[/]"

    def _row_sep(self) -> str:
        """Thin separator row inside a section."""
        return f"[#00cc00]│[dim]{'─' * self._W}[/]│[/]"

    # ── Arc-sweep inline knob ─────────────────────────────────────

    def _fmt_knob(self, value: float, min_val: float, max_val: float, label: str) -> str:
        """Two-line arc-sweep control."""
        norm = (value - min_val) / (max_val - min_val) if max_val > min_val else 0.0
        norm = max(0.0, min(1.0, norm))

        track_w = self._W - 2
        filled_f = norm * track_w
        full_blocks = int(filled_f)
        frac = filled_f - full_blocks
        empty_blocks = track_w - full_blocks - (1 if frac > 0 else 0)

        partials = " ▏▎▍▌▋▊▉"
        partial_char = partials[int(frac * 8)] if frac > 0 and full_blocks < track_w else ""

        filled = "█" * full_blocks
        empty  = "░" * max(0, empty_blocks)

        bar_line = (
            f"[#00cc00]│◖[/]"
            f"[#00dd00]{filled}[/]"
            f"[#336633]{partial_char}{empty}[/]"
            f"[#00cc00]◗│[/]"
        )

        lbl = label[: self._W]
        pad = self._W - len(lbl)
        lp, rp = pad // 2, pad - pad // 2
        label_line = f"[#00cc00]│[/]{' ' * lp}[bold #aaffaa]{lbl}[/]{' ' * rp}[#00cc00]│[/]"

        return f"{bar_line}\n{label_line}"

    # ── Time and frequency formatters ─────────────────────────────

    def _fmt_time(self, t: float) -> str:
        log_t = math.log10(max(0.001, t))
        log_min = math.log10(0.001)
        log_max = math.log10(5.0)
        norm = (log_t - log_min) / (log_max - log_min)
        label = f"{t * 1000:.0f}ms" if t < 1.0 else f"{t:.2f}s"
        return self._fmt_knob(norm, 0.0, 1.0, label)

    def _fmt_cutoff(self) -> str:
        log_c = math.log10(max(20.0, self.cutoff))
        log_min = math.log10(20.0)
        log_max = math.log10(20000.0)
        norm = (log_c - log_min) / (log_max - log_min)
        label = f"{self.cutoff / 1000:.2f}kHz" if self.cutoff >= 1000 else f"{self.cutoff:.0f}Hz"
        return self._fmt_knob(norm, 0.0, 1.0, label)

    def _fmt_resonance(self) -> str:
        return self._fmt_knob(self.resonance / 0.9, 0.0, 1.0, f"{int(self.resonance * 100)}%")

    # ── Waveform selector and shape display ───────────────────────

    def _fmt_waveform(self) -> str:
        entries = [
            ("pure_sine", "PSIN"),
            ("sine",      "SIN"),
            ("square",    "SQR"),
            ("sawtooth",  "SAW"),
            ("triangle",  "TRI"),
        ]
        parts = []
        for key, tag in entries:
            if self.waveform == key:
                parts.append(f"[bold #00ff00 reverse]{tag}[/]")
            else:
                parts.append(f"[#446644]{tag}[/]")
        line  = " ".join(parts)
        plain = " ".join(tag for _, tag in entries)
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

    def _fmt_waveform_shape(self) -> str:
        shapes = {
            "pure_sine": ("∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿", "#005500"),
            "sine":      ("∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿", "#005500"),
            "square":    ("⌐▀▀▀▀▀▀▀▀▀¬_________", "#005500"),
            "sawtooth":  ("/|/|/|/|/|/|/|/|/|/|", "#005500"),
            "triangle":  ("/\\/\\/\\/\\/\\/\\/\\/\\/\\/\\", "#005500"),
        }
        shape_str, color = shapes.get(self.waveform, ("~~~~~~~~~~~~~~~~~~~~", "#005500"))
        inner = self._W
        shape_str = shape_str[:inner].center(inner)
        return f"[#00cc00]│[/][{color}]{shape_str}[/][#00cc00]│[/]"

    def _fmt_dummy_selector(self, options: list, active: int) -> str:
        parts = []
        for i, opt in enumerate(options):
            if i == active:
                parts.append(f"[bold #00ff00 reverse]{opt}[/]")
            else:
                parts.append(f"[#446644]{opt}[/]")
        line  = " ".join(parts)
        plain = " ".join(options)
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

    # ── Octave display ────────────────────────────────────────────

    def _fmt_octave(self) -> str:
        feet      = {-2: "32'", -1: "16'", 0: "8'", 1: "4'", 2: "2'"}
        positions = [-2, -1, 0, 1, 2]
        norm      = (self.octave - (-2)) / (2 - (-2))

        track_w    = self._W - 2
        filled_f   = norm * track_w
        full_blocks = int(filled_f)
        frac        = filled_f - full_blocks
        empty_blocks = track_w - full_blocks - (1 if frac > 0 else 0)
        partials     = " ▏▎▍▌▋▊▉"
        partial_char = partials[int(frac * 8)] if frac > 0 and full_blocks < track_w else ""

        filled = "▪" * full_blocks
        empty  = "·" * max(0, empty_blocks)

        bar_line = (
            f"[#00cc00]│◖[/]"
            f"[#00dd00]{filled}[/]"
            f"[#336633]{partial_char}{empty}[/]"
            f"[#00cc00]◗│[/]"
        )

        dots = "  ".join(
            "[bold #00ff00]●[/]" if p == self.octave else "[#334433]○[/]"
            for p in positions
        )
        dots_plain = "  ".join("●" if p == self.octave else "○" for p in positions)
        dot_pad    = max(0, self._W - len(dots_plain))
        dlp, drp   = dot_pad // 2, dot_pad - dot_pad // 2
        dots_line  = f"[#00cc00]│[/]{' ' * dlp}{dots}{' ' * drp}[#00cc00]│[/]"

        label      = f"{feet.get(self.octave, '8')} ({self.octave:+d})"
        lpad       = max(0, self._W - len(label))
        llp, lrp   = lpad // 2, lpad - lpad // 2
        label_line = f"[#00cc00]│[/]{' ' * llp}[bold #aaffaa]{label}[/]{' ' * lrp}[#00cc00]│[/]"

        return f"{bar_line}\n{dots_line}\n{label_line}"

    # ── Help bar ─────────────────────────────────────────────────

    def _fmt_help_bar(self) -> str:
        """Dynamic help bar — shows section-specific keys when focused."""
        if not self._focused():
            return (
                "[#00aa00]PRESET[/] [dim],/.[/]cycle [dim]Ctrl+N/S[/]save  "
                "[#00aa00]OSC[/] [dim]Q/W[/]oct  "
                "[#00aa00]FLT[/] [dim]E/D[/]cut [dim]R/F[/]res  "
                "[#00aa00]ENV[/] [dim]T/G[/]atk [dim]Y/H[/]dec [dim]U/J[/]sus [dim]I/K[/]rel [dim]O/L[/]int  "
                "[#00aa00]MIX[/] [dim][][/]mvol  "
                "[#00aa00]FOCUS[/] [dim]↵[/]enter  "
                "[yellow][-][/]rnd  [dim]SPC[/]panic"
            )
        sec    = self._focus_section
        params = self._SECTION_PARAMS.get(sec, [])
        pidx   = self._focus_param
        pname  = params[pidx] if params else "—"
        plist  = "  ".join(
            f"[bold #00ffff]{p}[/]" if i == pidx else f"[dim]{p}[/]"
            for i, p in enumerate(params)
        )
        return (
            f"[bold #00ffff]◈ {sec.upper()}[/]  "
            f"{plist}  "
            f"[dim]←/→[/]section  [dim]↑/↓[/]param  "
            f"[bold #00ffff]Q[/][dim]-/[/][bold #00ffff]W[/][dim]+[/] or [bold #00ffff]Alt+←/→[/]  [bold #00ffff]{pname}[/] ±  "
            f"[dim],/.[/]preset  [dim]ESC[/]quit  [dim]↵[/]unfocus"
        )

    # ── Preset bar ────────────────────────────────────────────────

    def _fmt_preset_bar(self) -> str:
        total = self.preset_manager.count()
        if self._current_preset and total:
            idx   = self._preset_index + 1
            dirty = " [bold yellow]✱[/]" if self._dirty else ""
            return (
                f"[dim #00aa00]◄[/] [bold #00ff00]{self._current_preset.name}[/]{dirty}"
                f"  [dim]({idx}/{total})[/]"
                f"  [dim #00aa00]►[/]"
            )
        elif self._dirty:
            return "[bold yellow]✱ unsaved[/]"
        else:
            return "[dim]— no preset —[/]"
