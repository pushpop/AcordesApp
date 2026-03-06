"""Synth mode - Polyphonic synthesizer interface with preset management."""
import math
import random
import re
import time
from typing import TYPE_CHECKING, Optional

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

from music.synth_engine import SynthEngine
from music.preset_manager import PresetManager, Preset, DEFAULT_PARAMS, PARAM_KEYS
from music.factory_presets import get_factory_presets
from components.header_widget import HeaderWidget
from modes.preset_browser_modal import PresetBrowserScreen

if TYPE_CHECKING:
    from midi.input_handler import MIDIInputHandler
    from config_manager import ConfigManager


# ── Section navigation grid ───────────────────────────────────────────────────
# Sections arranged in visual order: row × col.
# Arrow keys move within this grid; wrapping is per-axis.
_SECTION_GRID = [
    ["oscillator", "filter", "filter_eg", "amp_eg"],  # row 0 — core signal chain (VCO→VCF→VCA)
    ["lfo", "chorus", "fx",  "arpeggio", "mixer"   ],  # row 1 — modulation + effects
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
        Binding("n", "open_preset_browser",  "Factory Presets",  show=False),
        # ── Focus-mode navigation (WASD) ──────────────────────────────────
        # W/S/A/D navigate the section grid only when in focus mode.
        # They are silently ignored when unfocused (no legacy fallback)
        # so they don't collide with note input or other shortcuts.
        Binding("w", "focus_nav_up",    "Focus nav ▲", show=False),
        Binding("s", "focus_nav_down",  "Focus nav ▼", show=False),
        Binding("a", "focus_nav_left",  "Focus nav ◄", show=False),
        Binding("d", "focus_nav_right", "Focus nav ►", show=False),
        # ── Focus-mode value keys ──────────────────────────────────────────
        # Q = decrease focused param, E = increase focused param.
        # In legacy mode Q adjusts octave down, E adjusts cutoff up (guarded).
        Binding("q", "param_down", "Param -", show=False),
        Binding("e", "param_up",   "Param +", show=False),
        # ── Focus-mode: randomize the currently highlighted parameter ──────
        # Shift+Minus sends the '_' character; Textual maps it to "underscore".
        Binding("underscore", "randomize_focused", "🎲 Rnd param", show=False),
        # ── Global ────────────────────────────────────────────────────────
        Binding("space", "panic",     "Panic (All Notes Off)", show=False),
        Binding("minus", "randomize", "🎲 Randomize",          show=False),
        Binding("i", "init_patch",   "Init Patch",            show=False),
        # Focus-mode: reset highlighted param to init value
        Binding("r", "reset_focused_param", "Reset param",    show=False),
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
        height: 1fr;
        padding: 0;
        margin: 0;
    }

    #synth-container {
        layout: horizontal;
        width: 100%;
        height: 20;
        padding: 0;
        margin: 0;
    }

    #synth-container-bottom {
        layout: horizontal;
        width: 100%;
        height: auto;
        padding: 0;
        margin-top: 3;
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

    #amp-eg-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }

    #filter-eg-section {
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

    .section-bottom {
        color: #00ff00;
        text-style: bold;
        padding: 0;
        margin: 0;
        width: 100%;
        height: auto;
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
    # Each entry: display label for the param row.
    # nav_up/down steps through these; dispatch in _adjust_focused_param uses the name.
    _SECTION_PARAMS = {
        "oscillator": ["Wave", "Noise", "Octave", "Drive"],
        "filter":     ["HPF Cut", "HPF Pk", "LPF Cut", "LPF Pk", "Route"],
        "amp_eg":     ["Attack", "Decay", "Sustain", "Release", "KTrack"],
        "filter_eg":  ["Atk", "Dcy", "Sus", "Rel", "Amount"],
        "lfo":        ["Rate", "Depth", "Shape", "Target"],
        "chorus":     ["Rate", "Depth", "Mix", "Voices"],
        "fx":         ["Delay Time", "Delay Fdbk", "Delay Mix", "Rev Size"],
        "arpeggio":   ["Mode", "BPM", "Gate", "Range", "ON/OFF"],
        "mixer":      ["Voice Type", "Amp", "Master Vol"],
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
        self._suggested_preset_name: Optional[str] = None  # Suggested name after randomization
        self._randomized_just_now: bool = False  # Show "🎲 Randomized!" in preset bar temporarily
        self._last_notification_time: float = 0.0  # Debounce notifications: only show one per 150ms

        params = self._load_initial_params()
        self.waveform   = params["waveform"]
        self.noise_level = params.get("noise_level", 0.0)
        self.octave     = params["octave"]
        self.amp_level  = params["amp_level"]
        self.cutoff       = params["cutoff"]
        self.hpf_cutoff   = params.get("hpf_cutoff", 20.0)
        self.resonance    = params["resonance"]
        self.hpf_resonance = params.get("hpf_resonance", 0.0)
        self.key_tracking = params.get("key_tracking", 0.5)
        self.filter_drive   = params.get("filter_drive",   1.0)
        self.filter_routing = params.get("filter_routing", "lp_hp")
        self.attack     = params["attack"]
        self.decay      = params["decay"]
        self.sustain    = params["sustain"]
        self.release    = params["release"]

        self.feg_attack  = params.get("feg_attack",  0.01)
        self.feg_decay   = params.get("feg_decay",   0.3)
        self.feg_sustain = params.get("feg_sustain", 0.0)
        self.feg_release = params.get("feg_release", 0.3)
        self.feg_amount  = params.get("feg_amount",  0.0)

        # ── LFO extended ─────────────────────────────────────────────────────
        self.lfo_freq   = params.get("lfo_freq",   1.0)
        self.lfo_depth  = params.get("lfo_depth",  0.0)
        self.lfo_shape  = params.get("lfo_shape",  "sine")
        self.lfo_target = params.get("lfo_target", "all")

        # ── FX Delay ─────────────────────────────────────────────────────────
        self.delay_time     = params.get("delay_time",     0.25)
        self.delay_feedback = params.get("delay_feedback", 0.3)
        self.delay_mix      = params.get("delay_mix",      0.0)

        # ── Chorus ───────────────────────────────────────────────────────────
        self.chorus_rate   = params.get("chorus_rate",   0.5)
        self.chorus_depth  = params.get("chorus_depth",  0.0)
        self.chorus_mix    = params.get("chorus_mix",    0.0)
        self.chorus_voices = params.get("chorus_voices", 2)

        # ── Arpeggiator ──────────────────────────────────────────────────────
        # BPM lives in config_manager (shared with MetronomeMode), not in presets
        self.arp_bpm     = float(self.config_manager.get_bpm())
        self.arp_enabled = params.get("arp_enabled", False)
        self.arp_mode    = params.get("arp_mode",    "up")
        self.arp_gate    = params.get("arp_gate",    0.5)
        self.arp_range   = params.get("arp_range",   1)

        # GLOBAL MASTER VOLUME (Persisted but not in presets)
        saved_state = self.config_manager.get_synth_state()
        self.master_volume = saved_state.get("master_volume", 1.0) if saved_state else 1.0
        self.voice_type = saved_state.get("voice_type", "poly") if saved_state else "poly"
        self.voice_type_display = None

        # ── Focus state ──────────────────────────────────────────────────────
        # _focus_section: which section is currently focused (None = global mode)
        # _focus_param:   index into _SECTION_PARAMS[section] for the active param
        self._focus_section: Optional[str] = None
        self._focus_param: int = 0

        # Focus-mode acceleration tracking — for smooth key-hold acceleration
        self._focus_adjust_start_time: Optional[float] = None  # When adjustment started
        self._focus_adjust_last_param_id: Optional[str] = None  # Last adjusted param (section+index)
        self._focus_accel_mult: float = 1.0  # Current acceleration multiplier for adjust methods

        # Noise parameter adaptive increment tracking
        self._noise_last_adjust_time = 0.0  # Timestamp of last adjustment
        self._noise_repeat_count = 0  # How many times adjusted in sequence
        self._NOISE_REPEAT_THRESHOLD = 0.15  # 150ms threshold for "held" detection

        # Widget references for live updates
        self.waveform_display       = None
        self.waveform_shape_display = None
        self.noise_display          = None
        self.octave_display         = None
        self.amp_display            = None
        self.master_volume_display  = None
        self.hpf_cutoff_display    = None
        self.hpf_resonance_display = None
        self.cutoff_display        = None
        self.resonance_display     = None
        self.key_tracking_display  = None
        self.filter_drive_display   = None
        self.filter_routing_display = None
        self.attack_display         = None
        self.decay_display          = None
        self.sustain_display        = None
        self.release_display        = None
        self.feg_attack_display  = None
        self.feg_decay_display   = None
        self.feg_sustain_display = None
        self.feg_release_display = None
        self.feg_amount_display  = None
        # LFO displays
        self.lfo_rate_display    = None
        self.lfo_depth_display   = None
        self.lfo_shape_display   = None
        self.lfo_target_display  = None
        # Chorus displays
        self.chorus_rate_display   = None
        self.chorus_depth_display  = None
        self.chorus_mix_display    = None
        self.chorus_voices_display = None
        # FX Delay displays
        self.delay_time_display     = None
        self.delay_feedback_display = None
        self.delay_mix_display      = None
        # Arpeggio displays
        self.arp_mode_display    = None
        self.arp_bpm_display     = None
        self.arp_gate_display    = None
        self.arp_range_display   = None
        self.arp_enabled_display = None
        self.header                 = None
        self.current_note: Optional[int] = None

        # IDs of the section-header Labels, keyed by section name.
        # Populated in compose(); used to re-render the header on focus change.
        self._section_header_ids: dict = {}

    def _load_initial_params(self) -> dict:
        # Load parameters in order: preset → synth_state → defaults
        # Synth state takes priority (preserves parameter tweaks even after preset load)
        out = dict(DEFAULT_PARAMS)

        # First: load preset if one was previously selected
        last_file = self.config_manager.get_last_preset()
        if last_file:
            idx = self.preset_manager.find_index_by_filename(last_file)
            if idx >= 0:
                preset = self.preset_manager.get(idx)
                self._current_preset = preset
                self._preset_index = idx
                self._dirty = False
                out.update(self.preset_manager.extract_params(preset))

        # Second: overlay synth_state on top (preserves individual tweaks)
        state = self.config_manager.get_synth_state()
        if state:
            out.update({k: state[k] for k in PARAM_KEYS if k in state})
            # If we had a preset loaded, tweaks make it dirty
            if self._current_preset:
                self._dirty = True

        return out

    def compose(self):
        self.header = HeaderWidget(
            title="S Y N T H   M O D E",
            #escondido para não criar conflito com o audio 
            #subtitle=self._get_status_text(),
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
                    yield Label(self._row_label("Noise", ""), classes="control-label", id="lbl-oscillator-1")
                    self.noise_display = Label(self._fmt_knob(self.noise_level, 0.0, 1.0, f"{int(self.noise_level * 100)}%"), classes="control-value", id="noise-display")
                    yield self.noise_display
                    yield Label(self._row_label("Octave", ""), classes="control-label", id="lbl-oscillator-2")
                    self.octave_display = Label(self._fmt_octave(), classes="control-value", id="octave-display")
                    yield self.octave_display
                    yield Label(self._row_label("Drive", ""), classes="control-label", id="lbl-oscillator-3")
                    self.filter_drive_display = Label(self._fmt_filter_drive(), classes="control-value", id="filter-drive-display")
                    yield self.filter_drive_display
                    yield Label(self._section_bottom(), classes="section-bottom")

                # ── FILTER ───────────────────────────────────────────────
                with Vertical(id="filter-section"):
                    hdr = Label(self._section_top("FILTER", False), classes="section-label", id="hdr-filter")
                    self._section_header_ids["filter"] = "hdr-filter"
                    yield hdr
                    yield Label(self._row_label("HPF Cut", ""), classes="control-label", id="lbl-filter-0")
                    self.hpf_cutoff_display = Label(self._fmt_hpf_cutoff(), classes="control-value", id="hpf-cutoff-display")
                    yield self.hpf_cutoff_display
                    yield Label(self._row_label("HPF Pk", ""), classes="control-label", id="lbl-filter-1")
                    self.hpf_resonance_display = Label(self._fmt_hpf_resonance(), classes="control-value", id="hpf-resonance-display")
                    yield self.hpf_resonance_display
                    yield Label(self._row_label("LPF Cut", ""), classes="control-label", id="lbl-filter-2")
                    self.cutoff_display = Label(self._fmt_cutoff(), classes="control-value", id="cutoff-display")
                    yield self.cutoff_display
                    yield Label(self._row_label("LPF Pk", ""), classes="control-label", id="lbl-filter-3")
                    self.resonance_display = Label(self._fmt_resonance(), classes="control-value", id="resonance-display")
                    yield self.resonance_display
                    yield Label(self._row_label("Route", ""), classes="control-label", id="lbl-filter-4")
                    self.filter_routing_display = Label(self._fmt_filter_routing(), classes="control-value", id="filter-routing-display")
                    yield self.filter_routing_display
                    yield Label(self._section_bottom(), classes="section-bottom")

                # ── FILTER EG ────────────────────────────────────────────
                with Vertical(id="filter-eg-section"):
                    hdr = Label(self._section_top("FILTER EG", False), classes="section-label", id="hdr-filter-eg")
                    self._section_header_ids["filter_eg"] = "hdr-filter-eg"
                    yield hdr
                    yield Label(self._row_label("Atk", ""), classes="control-label", id="lbl-filter-eg-0")
                    self.feg_attack_display = Label(self._fmt_time(self.feg_attack), classes="control-value", id="feg-attack-display")
                    yield self.feg_attack_display
                    yield Label(self._row_label("Dcy", ""), classes="control-label", id="lbl-filter-eg-1")
                    self.feg_decay_display = Label(self._fmt_time(self.feg_decay), classes="control-value", id="feg-decay-display")
                    yield self.feg_decay_display
                    yield Label(self._row_label("Sus", ""), classes="control-label", id="lbl-filter-eg-2")
                    self.feg_sustain_display = Label(self._fmt_knob(self.feg_sustain, 0.0, 1.0, f"{int(self.feg_sustain * 100)}%"), classes="control-value", id="feg-sustain-display")
                    yield self.feg_sustain_display
                    yield Label(self._row_label("Rel", ""), classes="control-label", id="lbl-filter-eg-3")
                    self.feg_release_display = Label(self._fmt_time(self.feg_release), classes="control-value", id="feg-release-display")
                    yield self.feg_release_display
                    yield Label(self._row_label("Amount", ""), classes="control-label", id="lbl-filter-eg-4")
                    self.feg_amount_display = Label(self._fmt_feg_amount(), classes="control-value", id="feg-amount-display")
                    yield self.feg_amount_display
                    yield Label(self._section_bottom(), classes="section-bottom")

                # ── AMP EG ───────────────────────────────────────────────
                with Vertical(id="amp-eg-section"):
                    hdr = Label(self._section_top("AMP EG", False), classes="section-label", id="hdr-amp-eg")
                    self._section_header_ids["amp_eg"] = "hdr-amp-eg"
                    yield hdr
                    yield Label(self._row_label("Attack", ""), classes="control-label", id="lbl-amp-eg-0")
                    self.attack_display = Label(self._fmt_time(self.attack), classes="control-value", id="attack-display")
                    yield self.attack_display
                    yield Label(self._row_label("Decay", ""), classes="control-label", id="lbl-amp-eg-1")
                    self.decay_display = Label(self._fmt_time(self.decay), classes="control-value", id="decay-display")
                    yield self.decay_display
                    yield Label(self._row_label("Sustain", ""), classes="control-label", id="lbl-amp-eg-2")
                    self.sustain_display = Label(
                        self._fmt_knob(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"),
                        classes="control-value", id="sustain-display")
                    yield self.sustain_display
                    yield Label(self._row_label("Release", ""), classes="control-label", id="lbl-amp-eg-3")
                    self.release_display = Label(self._fmt_time(self.release), classes="control-value", id="release-display")
                    yield self.release_display
                    yield Label(self._row_label("KTrack", ""), classes="control-label", id="lbl-amp-eg-4")
                    self.key_tracking_display = Label(self._fmt_key_tracking(), classes="control-value", id="key-tracking-display")
                    yield self.key_tracking_display
                    yield Label(self._section_bottom(), classes="section-bottom")

            # ── SPACING ───────────────────────────────────────────────────
            yield Label("")
            yield Label("")
            yield Label("")

            # ── ROW 2: LFO · CHORUS · FX · ARPEGGIO · MIXER ────────────
            with Horizontal(id="synth-container-bottom"):

                # ── LFO ──────────────────────────────────────────────────
                with Vertical(id="lfo-section"):
                    hdr = Label(self._section_top("LFO", False), classes="section-label", id="hdr-lfo")
                    self._section_header_ids["lfo"] = "hdr-lfo"
                    yield hdr
                    yield Label(self._row_label("Rate", ""), classes="control-label", id="lbl-lfo-0")
                    self.lfo_rate_display = Label(self._fmt_lfo_rate(), classes="control-value", id="lfo-rate-display")
                    yield self.lfo_rate_display
                    yield Label(self._row_label("Depth", ""), classes="control-label", id="lbl-lfo-1")
                    self.lfo_depth_display = Label(self._fmt_knob(self.lfo_depth, 0.0, 1.0, f"{int(self.lfo_depth * 100)}%"), classes="control-value", id="lfo-depth-display")
                    yield self.lfo_depth_display
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Shape", ""), classes="control-label", id="lbl-lfo-2")
                    self.lfo_shape_display = Label(self._fmt_lfo_shape(), classes="control-value", id="lfo-shape-display")
                    yield self.lfo_shape_display
                    yield Label(self._row_label("Target", ""), classes="control-label", id="lbl-lfo-3")
                    self.lfo_target_display = Label(self._fmt_lfo_target(), classes="control-value", id="lfo-target-display")
                    yield self.lfo_target_display
                    yield Label(self._section_bottom(), classes="section-bottom")

                # ── CHORUS ───────────────────────────────────────────────
                with Vertical(id="chorus-section"):
                    hdr = Label(self._section_top("CHORUS", False), classes="section-label", id="hdr-chorus")
                    self._section_header_ids["chorus"] = "hdr-chorus"
                    yield hdr
                    yield Label(self._row_label("Rate", ""), classes="control-label", id="lbl-chorus-0")
                    self.chorus_rate_display = Label(self._fmt_chorus_rate(), classes="control-value", id="chorus-rate-display")
                    yield self.chorus_rate_display
                    yield Label(self._row_label("Depth", ""), classes="control-label", id="lbl-chorus-1")
                    self.chorus_depth_display = Label(self._fmt_knob(self.chorus_depth, 0.0, 1.0, f"{int(self.chorus_depth * 100)}%"), classes="control-value", id="chorus-depth-display")
                    yield self.chorus_depth_display
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Mix", ""), classes="control-label", id="lbl-chorus-2")
                    self.chorus_mix_display = Label(self._fmt_knob(self.chorus_mix, 0.0, 1.0, f"{int(self.chorus_mix * 100)}%"), classes="control-value", id="chorus-mix-display")
                    yield self.chorus_mix_display
                    yield Label(self._row_label("Voices", ""), classes="control-label", id="lbl-chorus-3")
                    self.chorus_voices_display = Label(self._fmt_chorus_voices(), classes="control-value", id="chorus-voices-display")
                    yield self.chorus_voices_display
                    yield Label(self._section_bottom(), classes="section-bottom")

                # ── FX ───────────────────────────────────────────────────
                with Vertical(id="fx-section"):
                    hdr = Label(self._section_top("FX", False), classes="section-label", id="hdr-fx")
                    self._section_header_ids["fx"] = "hdr-fx"
                    yield hdr
                    yield Label(self._row_label("Delay Time", ""), classes="control-label", id="lbl-fx-0")
                    self.delay_time_display = Label(self._fmt_delay_time(), classes="control-value", id="delay-time-display")
                    yield self.delay_time_display
                    yield Label(self._row_label("Delay Fdbk", ""), classes="control-label", id="lbl-fx-1")
                    self.delay_feedback_display = Label(self._fmt_knob(self.delay_feedback, 0.0, 0.9, f"{int(self.delay_feedback * 100)}%"), classes="control-value", id="delay-feedback-display")
                    yield self.delay_feedback_display
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Delay Mix", ""), classes="control-label", id="lbl-fx-2")
                    self.delay_mix_display = Label(self._fmt_knob(self.delay_mix, 0.0, 1.0, f"{int(self.delay_mix * 100)}%"), classes="control-value", id="delay-mix-display")
                    yield self.delay_mix_display
                    yield Label(self._row_label("Rev Size", ""), classes="control-label", id="lbl-fx-3")
                    yield Label(self._fmt_disabled_param("future"), classes="control-value")
                    yield Label(self._section_bottom(), classes="section-bottom")

                # ── ARPEGGIO ─────────────────────────────────────────────
                with Vertical(id="arpeggio-section"):
                    hdr = Label(self._section_top("ARPEGGIO", False), classes="section-label", id="hdr-arpeggio")
                    self._section_header_ids["arpeggio"] = "hdr-arpeggio"
                    yield hdr
                    yield Label(self._row_label("Mode", ""), classes="control-label", id="lbl-arpeggio-0")
                    self.arp_mode_display = Label(self._fmt_arp_mode(), classes="control-value", id="arp-mode-display")
                    yield self.arp_mode_display
                    yield Label(self._row_label("BPM", ""), classes="control-label", id="lbl-arpeggio-1")
                    self.arp_bpm_display = Label(self._fmt_knob(self.arp_bpm, 50.0, 300.0, f"{int(self.arp_bpm)} BPM"), classes="control-value", id="arp-bpm-display")
                    yield self.arp_bpm_display
                    yield Label(self._row_sep(), classes="control-label")
                    yield Label(self._row_label("Gate", ""), classes="control-label", id="lbl-arpeggio-2")
                    self.arp_gate_display = Label(self._fmt_knob(self.arp_gate, 0.05, 1.0, f"{int(self.arp_gate * 100)}%"), classes="control-value", id="arp-gate-display")
                    yield self.arp_gate_display
                    yield Label(self._row_label("Range", ""), classes="control-label", id="lbl-arpeggio-3")
                    self.arp_range_display = Label(self._fmt_arp_range(), classes="control-value", id="arp-range-display")
                    yield self.arp_range_display
                    yield Label(self._row_label("ON/OFF", ""), classes="control-label", id="lbl-arpeggio-4")
                    self.arp_enabled_display = Label(self._fmt_bool_toggle(self.arp_enabled, "ARP ON", "ARP OFF"), classes="control-value", id="arp-enabled-display")
                    yield self.arp_enabled_display
                    yield Label(self._section_bottom(), classes="section-bottom")

                # ── MIXER ────────────────────────────────────────────────
                with Vertical(id="mixer-section"):
                    hdr = Label(self._section_top("MIXER", False), classes="section-label", id="hdr-mixer")
                    self._section_header_ids["mixer"] = "hdr-mixer"
                    yield hdr

                    # Voice Type (top)
                    yield Label(self._row_label("Voice Type", ""), classes="control-label", id="lbl-mixer-0")
                    self.voice_type_display = Label(
                        self._fmt_voice_type(),
                        classes="control-value", id="voice-type-display")
                    yield self.voice_type_display
                    yield Label(self._row_sep(), classes="control-label")

                    # Amp (middle)
                    yield Label(self._row_label("Amp", ""), classes="control-label", id="lbl-mixer-1")
                    self.amp_display = Label(
                        self._fmt_knob(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%"),
                        classes="control-value", id="amp-display")
                    yield self.amp_display
                    yield Label(self._row_sep(), classes="control-label")

                    # Master Vol (bottom)
                    yield Label(self._row_label("Master Vol", ""), classes="control-label", id="lbl-mixer-2")
                    self.master_volume_display = Label(
                        self._fmt_knob(self.master_volume, 0.0, 1.0, f"{int(self.master_volume * 100)}%"),
                        classes="control-value", id="master-volume-display")
                    yield self.master_volume_display
                    yield Label(self._section_bottom(), classes="section-bottom")

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

    # ── Notifications (debounced to prevent stacking) ──────────────

    def _show_notification(self, message: str, severity: str = "information", timeout: float = 2.0):
        """Show a notification only if 150ms has elapsed since the last one.
        This prevents rapid notifications from stacking on top of each other."""
        now = time.time()
        if now - self._last_notification_time >= 0.15:
            self._last_notification_time = now
            self.app.notify(message, severity=severity, timeout=timeout)

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
            title = section.replace("_", " ").upper()
            lbl.update(self._section_top(title, self._focus_section == section))
        except Exception:
            pass

    def _redraw_param_labels(self, section: str):
        """Re-render every param-row label in section with focus highlight."""
        params = self._SECTION_PARAMS.get(section, [])
        for idx, name in enumerate(params):
            wid_id = f"lbl-{section.replace('_', '-')}-{idx}"
            try:
                lbl = self.query_one(f"#{wid_id}", Label)
                active = (self._focus_section == section and self._focus_param == idx)
                lbl.update(self._row_label(name, "", active=active))
            except Exception:
                pass

    def _redraw_help_bar(self):
        """No-op: help bar is now managed by MainScreen."""
        pass

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
            c = min(c, len(_SECTION_GRID[nr]) - 1)
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
            c = min(c, len(_SECTION_GRID[nr]) - 1)
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

    # ── WASD — focus-only navigation (silently ignored when unfocused) ────

    def action_focus_nav_up(self):
        """W — move highlight up within focused section (focus mode only)."""
        if self._focused():
            self.action_nav_up()

    def action_focus_nav_down(self):
        """S — move highlight down within focused section (focus mode only)."""
        if self._focused():
            self.action_nav_down()

    def action_focus_nav_left(self):
        """A — move to section on the left (focus mode only)."""
        if self._focused():
            self.action_nav_left()

    def action_focus_nav_right(self):
        """D — move to section on the right (focus mode only)."""
        if self._focused():
            self.action_nav_right()

    # ── Q / E  →  param_down / param_up (focus mode) ─────────────
    # Legacy unfocused fallback: Q = octave down, E = cutoff up.
    # In focus mode both keys adjust the highlighted parameter instead.

    def action_adjust_focused(self, direction: str = "up"):
        """Alt+Left/Right — adjust the currently focused parameter."""
        if self._focused():
            self._adjust_focused_param(direction)

    def action_param_up(self):
        """E — increase focused param in focus mode; cutoff up in legacy mode."""
        if self._focused():
            self._adjust_focused_param("up")
        else:
            self._do_adjust_cutoff("up")

    def action_param_down(self):
        """Q — decrease focused param in focus mode; octave down in legacy mode."""
        if self._focused():
            self._adjust_focused_param("down")
        else:
            self._do_adjust_octave("down")

    def _calc_focus_adjustment_acceleration(self) -> float:
        """Calculate exponential acceleration multiplier for focus-mode parameter adjustments.

        Acceleration curve:
        - 0-1000ms: 1.0× (very long dead zone — protects all normal interactions)
        - 1000ms+: multiplier = 1.0 + ((hold_time - 1000ms) / 2500ms)^1.5
        - Capped at 2.0× max (minimal acceleration)

        Resets when switching to a different parameter.
        """
        import time

        # Identify current parameter
        param_id = f"{self._focus_section}:{self._focus_param}"

        # Check if we switched parameters
        if param_id != self._focus_adjust_last_param_id:
            self._focus_adjust_start_time = None  # Reset timer
            self._focus_adjust_last_param_id = param_id

        # Initialize timer on first adjustment
        if self._focus_adjust_start_time is None:
            self._focus_adjust_start_time = time.time()
            return 1.0

        # Calculate hold time in milliseconds
        hold_time_ms = (time.time() - self._focus_adjust_start_time) * 1000

        # Dead zone: no acceleration for first 1000ms (protects normal tapping and adjustments)
        if hold_time_ms < 1000:
            return 1.0

        # Acceleration phase: extremely gentle curve with very long time constant
        accel_elapsed = hold_time_ms - 1000  # Time since acceleration started
        multiplier = 1.0 + ((accel_elapsed / 2500.0) ** 1.5)  # Extremely slow ramp: 2500ms time constant

        return min(multiplier, 2.0)  # Cap at 2.0× maximum (minimal acceleration)

    def _adjust_focused_param(self, direction: str):
        """Dispatch to the correct adjustment action for the focused param.
        Calls _do_* helpers that bypass the focus guard on action methods."""
        sec   = self._focus_section
        pidx  = self._focus_param
        params = self._SECTION_PARAMS.get(sec, [])
        if not params or pidx >= len(params):
            return
        name = params[pidx]

        # Calculate and store acceleration multiplier for this adjustment
        self._focus_accel_mult = self._calc_focus_adjustment_acceleration()

        # OSC
        if sec == "oscillator":
            if name == "Wave":
                self._do_toggle_waveform("forward" if direction == "up" else "backward")
            elif name == "Noise":
                self._do_adjust_noise_level(direction)
            elif name == "Octave":
                self._do_adjust_octave(direction)
            elif name == "Drive":
                self._do_adjust_filter_drive(direction)
        # FILTER
        elif sec == "filter":
            if name == "HPF Cut":   self._do_adjust_hpf_cutoff(direction)
            elif name == "HPF Pk":  self._do_adjust_hpf_resonance(direction)
            elif name == "LPF Cut": self._do_adjust_cutoff(direction)
            elif name == "LPF Pk":  self._do_adjust_resonance(direction)
            elif name == "Route":   self._do_cycle_filter_routing(direction)
        # AMP EG
        elif sec == "amp_eg":
            if name == "Attack":      self._do_adjust_attack(direction)
            elif name == "Decay":     self._do_adjust_decay(direction)
            elif name == "Sustain":   self._do_adjust_sustain(direction)
            elif name == "Release":   self._do_adjust_release(direction)
            elif name == "KTrack":    self._do_step_key_tracking(direction)
        # FILTER EG
        elif sec == "filter_eg":
            if name == "Atk":    self._do_adjust_feg_attack(direction)
            elif name == "Dcy":  self._do_adjust_feg_decay(direction)
            elif name == "Sus":  self._do_adjust_feg_sustain(direction)
            elif name == "Rel":  self._do_adjust_feg_release(direction)
            elif name == "Amount": self._do_adjust_feg_amount(direction)
        # MIXER
        elif sec == "mixer":
            if name == "Voice Type":   self._do_adjust_voice_type(direction)
            elif name == "Amp":        self._do_adjust_volume(direction)
            elif name == "Master Vol": self._do_adjust_master_volume(direction)
        # LFO
        elif sec == "lfo":
            if name == "Rate":    self._do_adjust_lfo_rate(direction)
            elif name == "Depth": self._do_adjust_lfo_depth(direction)
            elif name == "Shape": self._do_cycle_lfo_shape(direction)
            elif name == "Target": self._do_cycle_lfo_target(direction)
        # CHORUS
        elif sec == "chorus":
            if name == "Rate":    self._do_adjust_chorus_rate(direction)
            elif name == "Depth": self._do_adjust_chorus_depth(direction)
            elif name == "Mix":   self._do_adjust_chorus_mix(direction)
            elif name == "Voices": self._do_adjust_chorus_voices(direction)
        # FX DELAY
        elif sec == "fx":
            if name == "Delay Time":  self._do_adjust_delay_time(direction)
            elif name == "Delay Fdbk": self._do_adjust_delay_feedback(direction)
            elif name == "Delay Mix":  self._do_adjust_delay_mix(direction)
            elif name == "Rev Size":   pass   # future placeholder — no-op
        # ARPEGGIO
        elif sec == "arpeggio":
            if name == "Mode":    self._do_cycle_arp_mode(direction)
            elif name == "BPM":   self._do_adjust_arp_bpm(direction)
            elif name == "Gate":  self._do_adjust_arp_gate(direction)
            elif name == "Range": self._do_adjust_arp_range(direction)
            elif name == "ON/OFF": self._do_toggle_arp_enabled()

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

    def _do_adjust_noise_level(self, direction: str = "up"):
        """Adjust noise mix level (0.0 - 1.0) with adaptive step size based on repeat frequency."""
        import time
        current_time = time.time()
        time_since_last = current_time - self._noise_last_adjust_time

        # Determine step size: small (0.01) for first press, large (0.05) if rapidly repeated
        if time_since_last < self._NOISE_REPEAT_THRESHOLD:
            self._noise_repeat_count += 1
            step = 0.05 if self._noise_repeat_count > 2 else 0.01  # After 3rd quick press, use larger step
        else:
            self._noise_repeat_count = 0
            step = 0.01  # Start with fine increments

        # Apply adjustment
        if direction == "up":
            self.noise_level = min(1.0, self.noise_level + step)
        else:
            self.noise_level = max(0.0, self.noise_level - step)

        self._noise_last_adjust_time = current_time
        self.synth_engine.update_parameters(noise_level=self.noise_level)
        if self.noise_display:
            self.noise_display.update(self._fmt_knob(self.noise_level, 0.0, 1.0, f"{int(self.noise_level * 100)}%"))
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
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.amp_level = min(1.0, self.amp_level + step) if direction == "up" else max(0.0, self.amp_level - step)
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

    def _do_adjust_voice_type(self, direction: str = "right"):
        """Cycle through voice type modes: mono → poly → unison → mono"""
        modes = ["mono", "poly", "unison"]
        try:
            idx = modes.index(self.voice_type.lower())
        except (ValueError, AttributeError):
            idx = 1  # Default to poly

        if direction == "right" or direction == "up":
            idx = (idx + 1) % len(modes)
        else:  # left or down
            idx = (idx - 1) % len(modes)

        self.voice_type = modes[idx]
        self.synth_engine.update_parameters(voice_type=self.voice_type)
        if self.voice_type_display:
            self.voice_type_display.update(self._fmt_voice_type())
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_cutoff(self, direction: str = "up"):
        accel_ratio = 1.1 ** self._focus_accel_mult if self._focus_accel_mult > 1.0 else 1.1
        self.cutoff = min(20000.0, self.cutoff * accel_ratio) if direction == "up" else max(20.0, self.cutoff / accel_ratio)
        self.synth_engine.update_parameters(cutoff=self.cutoff)
        if self.cutoff_display:
            self.cutoff_display.update(self._fmt_cutoff())
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_resonance(self, direction: str = "up"):
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.resonance = min(0.80, self.resonance + step) if direction == "up" else max(0.0, self.resonance - step)
        self.synth_engine.update_parameters(resonance=self.resonance)
        if self.resonance_display:
            self.resonance_display.update(self._fmt_resonance())
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_hpf_cutoff(self, direction: str = "up"):
        accel_ratio = 1.15 ** self._focus_accel_mult if self._focus_accel_mult > 1.0 else 1.15
        self.hpf_cutoff = min(4000.0, self.hpf_cutoff * accel_ratio) if direction == "up" else max(20.0, self.hpf_cutoff / accel_ratio)
        self.synth_engine.update_parameters(hpf_cutoff=self.hpf_cutoff)
        if self.hpf_cutoff_display:
            self.hpf_cutoff_display.update(self._fmt_hpf_cutoff())
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_hpf_resonance(self, direction: str = "up"):
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.hpf_resonance = min(0.85, self.hpf_resonance + step) if direction == "up" else max(0.0, self.hpf_resonance - step)
        self.synth_engine.update_parameters(hpf_resonance=self.hpf_resonance)
        if self.hpf_resonance_display:
            self.hpf_resonance_display.update(self._fmt_hpf_resonance())
        self._mark_dirty()
        self._autosave_state()

    # Key tracking cycles through 5 discrete steps (0%, 25%, 50%, 75%, 100%)
    _KEY_TRACKING_STEPS = [0.0, 0.25, 0.5, 0.75, 1.0]

    def _do_step_key_tracking(self, direction: str = "up"):
        steps = self._KEY_TRACKING_STEPS
        # Find the nearest step index to the current value
        idx = min(range(len(steps)), key=lambda i: abs(steps[i] - self.key_tracking))
        if direction == "up":
            idx = min(len(steps) - 1, idx + 1)
        else:
            idx = max(0, idx - 1)
        self.key_tracking = steps[idx]
        self.synth_engine.update_parameters(key_tracking=self.key_tracking)
        if self.key_tracking_display:
            self.key_tracking_display.update(self._fmt_key_tracking())
        self._mark_dirty()
        self._autosave_state()

    _FILTER_ROUTING_OPTIONS = ["lp_hp", "bp_lp", "notch_lp", "lp_lp"]

    def _do_adjust_filter_drive(self, direction: str = "up"):
        step = 0.1 * self._focus_accel_mult
        if direction == "up":
            self.filter_drive = min(8.0, round(self.filter_drive + step, 2))
        else:
            self.filter_drive = max(0.5, round(self.filter_drive - step, 2))
        self.synth_engine.update_parameters(filter_drive=self.filter_drive)
        if self.filter_drive_display:
            self.filter_drive_display.update(self._fmt_filter_drive())
        self._mark_dirty()
        self._autosave_state()

    def _do_cycle_filter_routing(self, direction: str = "up"):
        opts = self._FILTER_ROUTING_OPTIONS
        idx = opts.index(self.filter_routing) if self.filter_routing in opts else 0
        if direction == "up":
            idx = (idx + 1) % len(opts)
        else:
            idx = (idx - 1) % len(opts)
        self.filter_routing = opts[idx]
        self.synth_engine.update_parameters(filter_routing=self.filter_routing)
        if self.filter_routing_display:
            self.filter_routing_display.update(self._fmt_filter_routing())
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_attack(self, direction: str = "up"):
        # Apply acceleration multiplier to the adjustment ratio (for focus-mode smooth acceleration)
        accel_ratio = 1.15 ** self._focus_accel_mult if self._focus_accel_mult > 1.0 else 1.15
        self.attack = min(5.0, self.attack * accel_ratio) if direction == "up" else max(0.008, self.attack / accel_ratio)
        self.synth_engine.update_parameters(attack=self.attack)
        if self.attack_display:
            self.attack_display.update(self._fmt_time(self.attack))
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_decay(self, direction: str = "up"):
        accel_ratio = 1.15 ** self._focus_accel_mult if self._focus_accel_mult > 1.0 else 1.15
        self.decay = min(5.0, self.decay * accel_ratio) if direction == "up" else max(0.005, self.decay / accel_ratio)
        self.synth_engine.update_parameters(decay=self.decay)
        if self.decay_display:
            self.decay_display.update(self._fmt_time(self.decay))
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_sustain(self, direction: str = "up"):
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.sustain = min(1.0, self.sustain + step) if direction == "up" else max(0.0, self.sustain - step)
        self.synth_engine.update_parameters(sustain=self.sustain)
        if self.sustain_display:
            self.sustain_display.update(self._fmt_knob(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"))
        self._mark_dirty()
        self._autosave_state()

    def _do_adjust_release(self, direction: str = "up"):
        accel_ratio = 1.15 ** self._focus_accel_mult if self._focus_accel_mult > 1.0 else 1.15
        self.release = min(5.0, self.release * accel_ratio) if direction == "up" else max(0.008, self.release / accel_ratio)
        self.synth_engine.update_parameters(release=self.release)
        if self.release_display:
            self.release_display.update(self._fmt_time(self.release))
        self._mark_dirty()
        self._autosave_state()

    # ── LFO mutators ─────────────────────────────────────────────

    def _do_adjust_lfo_rate(self, direction: str = "up"):
        accel_ratio = 1.2 ** self._focus_accel_mult if self._focus_accel_mult > 1.0 else 1.2
        self.lfo_freq = min(20.0, self.lfo_freq * accel_ratio) if direction == "up" else max(0.05, self.lfo_freq / accel_ratio)
        self.synth_engine.update_parameters(lfo_freq=self.lfo_freq)
        if self.lfo_rate_display:
            self.lfo_rate_display.update(self._fmt_lfo_rate())
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_lfo_depth(self, direction: str = "up"):
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.lfo_depth = min(1.0, self.lfo_depth + step) if direction == "up" else max(0.0, self.lfo_depth - step)
        self.synth_engine.update_parameters(lfo_depth=self.lfo_depth)
        if self.lfo_depth_display:
            self.lfo_depth_display.update(self._fmt_knob(self.lfo_depth, 0.0, 1.0, f"{int(self.lfo_depth * 100)}%"))
        self._mark_dirty(); self._autosave_state()

    def _do_cycle_lfo_shape(self, direction: str = "up"):
        shapes = ["sine", "triangle", "square", "sample_hold"]
        delta = 1 if direction == "up" else -1
        idx = shapes.index(self.lfo_shape) if self.lfo_shape in shapes else 0
        self.lfo_shape = shapes[(idx + delta) % len(shapes)]
        self.synth_engine.update_parameters(lfo_shape=self.lfo_shape)
        if self.lfo_shape_display:
            self.lfo_shape_display.update(self._fmt_lfo_shape())
        self._mark_dirty(); self._autosave_state()

    def _do_cycle_lfo_target(self, direction: str = "up"):
        targets = ["all", "vco", "vcf", "vca"]
        delta = 1 if direction == "up" else -1
        idx = targets.index(self.lfo_target) if self.lfo_target in targets else 0
        self.lfo_target = targets[(idx + delta) % len(targets)]
        self.synth_engine.update_parameters(lfo_target=self.lfo_target)
        if self.lfo_target_display:
            self.lfo_target_display.update(self._fmt_lfo_target())
        self._mark_dirty(); self._autosave_state()

    # ── Chorus mutators ───────────────────────────────────────────

    def _do_adjust_chorus_rate(self, direction: str = "up"):
        self.chorus_rate = min(10.0, self.chorus_rate * 1.2) if direction == "up" else max(0.1, self.chorus_rate / 1.2)
        self.synth_engine.update_parameters(chorus_rate=self.chorus_rate)
        if self.chorus_rate_display:
            self.chorus_rate_display.update(self._fmt_chorus_rate())
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_chorus_depth(self, direction: str = "up"):
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.chorus_depth = min(1.0, self.chorus_depth + step) if direction == "up" else max(0.0, self.chorus_depth - step)
        self.synth_engine.update_parameters(chorus_depth=self.chorus_depth)
        if self.chorus_depth_display:
            self.chorus_depth_display.update(self._fmt_knob(self.chorus_depth, 0.0, 1.0, f"{int(self.chorus_depth * 100)}%"))
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_chorus_mix(self, direction: str = "up"):
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.chorus_mix = min(1.0, self.chorus_mix + step) if direction == "up" else max(0.0, self.chorus_mix - step)
        self.synth_engine.update_parameters(chorus_mix=self.chorus_mix)
        if self.chorus_mix_display:
            self.chorus_mix_display.update(self._fmt_knob(self.chorus_mix, 0.0, 1.0, f"{int(self.chorus_mix * 100)}%"))
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_chorus_voices(self, direction: str = "up"):
        self.chorus_voices = min(4, self.chorus_voices + 1) if direction == "up" else max(1, self.chorus_voices - 1)
        self.synth_engine.update_parameters(chorus_voices=self.chorus_voices)
        if self.chorus_voices_display:
            self.chorus_voices_display.update(self._fmt_chorus_voices())
        self._mark_dirty(); self._autosave_state()

    # ── FX Delay mutators ─────────────────────────────────────────

    def _do_adjust_delay_time(self, direction: str = "up"):
        self.delay_time = min(2.0, self.delay_time + 0.025) if direction == "up" else max(0.05, self.delay_time - 0.025)
        self.synth_engine.update_parameters(delay_time=self.delay_time)
        if self.delay_time_display:
            self.delay_time_display.update(self._fmt_delay_time())
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_delay_feedback(self, direction: str = "up"):
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.delay_feedback = min(0.9, self.delay_feedback + step) if direction == "up" else max(0.0, self.delay_feedback - step)
        self.synth_engine.update_parameters(delay_feedback=self.delay_feedback)
        if self.delay_feedback_display:
            self.delay_feedback_display.update(self._fmt_knob(self.delay_feedback, 0.0, 0.9, f"{int(self.delay_feedback * 100)}%"))
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_delay_mix(self, direction: str = "up"):
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.delay_mix = min(1.0, self.delay_mix + step) if direction == "up" else max(0.0, self.delay_mix - step)
        self.synth_engine.update_parameters(delay_mix=self.delay_mix)
        if self.delay_mix_display:
            self.delay_mix_display.update(self._fmt_knob(self.delay_mix, 0.0, 1.0, f"{int(self.delay_mix * 100)}%"))
        self._mark_dirty(); self._autosave_state()

    # ── Arpeggio mutators ─────────────────────────────────────────

    def _do_cycle_arp_mode(self, direction: str = "up"):
        modes = ["up", "down", "up_down", "random"]
        delta = 1 if direction == "up" else -1
        idx = modes.index(self.arp_mode) if self.arp_mode in modes else 0
        self.arp_mode = modes[(idx + delta) % len(modes)]
        self.synth_engine.update_parameters(arp_mode=self.arp_mode)
        if self.arp_mode_display:
            self.arp_mode_display.update(self._fmt_arp_mode())
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_arp_bpm(self, direction: str = "up"):
        step = 5
        self.arp_bpm = min(300.0, self.arp_bpm + step) if direction == "up" else max(50.0, self.arp_bpm - step)
        self.config_manager.set_bpm(int(self.arp_bpm))
        self.synth_engine.update_parameters(arp_bpm=self.arp_bpm)
        if self.arp_bpm_display:
            self.arp_bpm_display.update(self._fmt_knob(self.arp_bpm, 50.0, 300.0, f"{int(self.arp_bpm)} BPM"))
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_arp_gate(self, direction: str = "up"):
        step = 0.01 * self._focus_accel_mult  # Apply focus-mode acceleration to step (0.01 = 1% for ultra-fine control)
        self.arp_gate = min(1.0, self.arp_gate + step) if direction == "up" else max(0.05, self.arp_gate - step)
        self.synth_engine.update_parameters(arp_gate=self.arp_gate)
        if self.arp_gate_display:
            self.arp_gate_display.update(self._fmt_knob(self.arp_gate, 0.05, 1.0, f"{int(self.arp_gate * 100)}%"))
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_arp_range(self, direction: str = "up"):
        self.arp_range = min(4, self.arp_range + 1) if direction == "up" else max(1, self.arp_range - 1)
        self.synth_engine.update_parameters(arp_range=self.arp_range)
        if self.arp_range_display:
            self.arp_range_display.update(self._fmt_arp_range())
        self._mark_dirty(); self._autosave_state()

    def _do_toggle_arp_enabled(self):
        self.arp_enabled = not self.arp_enabled
        self.synth_engine.update_parameters(arp_enabled=self.arp_enabled)
        if self.arp_enabled_display:
            self.arp_enabled_display.update(self._fmt_bool_toggle(self.arp_enabled, "ARP ON", "ARP OFF"))
        self._mark_dirty(); self._autosave_state()

    # ── Filter EG mutators ────────────────────────────────────────

    def _do_adjust_feg_attack(self, direction: str):
        step = 0.01 if self.feg_attack < 0.1 else (0.05 if self.feg_attack < 1.0 else 0.1)
        step *= self._focus_accel_mult  # Apply focus-mode acceleration
        self.feg_attack = max(0.008, min(4.0, self.feg_attack + (step if direction == "up" else -step)))
        self.synth_engine.update_parameters(feg_attack=self.feg_attack)
        if self.feg_attack_display: self.feg_attack_display.update(self._fmt_time(self.feg_attack))
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_feg_decay(self, direction: str):
        step = 0.01 if self.feg_decay < 0.1 else (0.05 if self.feg_decay < 1.0 else 0.1)
        step *= self._focus_accel_mult  # Apply focus-mode acceleration
        self.feg_decay = max(0.005, min(4.0, self.feg_decay + (step if direction == "up" else -step)))
        self.synth_engine.update_parameters(feg_decay=self.feg_decay)
        if self.feg_decay_display: self.feg_decay_display.update(self._fmt_time(self.feg_decay))
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_feg_sustain(self, direction: str):
        self.feg_sustain = max(0.0, min(1.0, self.feg_sustain + (0.05 if direction == "up" else -0.05)))
        self.synth_engine.update_parameters(feg_sustain=self.feg_sustain)
        if self.feg_sustain_display: self.feg_sustain_display.update(self._fmt_knob(self.feg_sustain, 0.0, 1.0, f"{int(self.feg_sustain * 100)}%"))
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_feg_release(self, direction: str):
        step = 0.01 if self.feg_release < 0.1 else (0.05 if self.feg_release < 1.0 else 0.1)
        step *= self._focus_accel_mult  # Apply focus-mode acceleration
        self.feg_release = max(0.005, min(4.0, self.feg_release + (step if direction == "up" else -step)))
        self.synth_engine.update_parameters(feg_release=self.feg_release)
        if self.feg_release_display: self.feg_release_display.update(self._fmt_time(self.feg_release))
        self._mark_dirty(); self._autosave_state()

    def _do_adjust_feg_amount(self, direction: str):
        self.feg_amount = max(-1.0, min(1.0, self.feg_amount + (0.05 if direction == "up" else -0.05)))
        self.synth_engine.update_parameters(feg_amount=self.feg_amount)
        if self.feg_amount_display: self.feg_amount_display.update(self._fmt_feg_amount())
        self._mark_dirty(); self._autosave_state()

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
        # Use suggested name if available (from randomization), otherwise generate new one
        preset = self.preset_manager.save_new(params, name=self._suggested_preset_name)
        self._current_preset = preset
        self._preset_index = self.preset_manager.find_index_by_filename(preset.filename)
        self._dirty = False
        self._suggested_preset_name = None  # Clear suggested name after saving
        self.config_manager.set_last_preset(preset.filename)
        self._update_preset_ui()
        self._show_notification(f'💾 Saved: "{preset.name}"', timeout=3)

    def action_save_preset_overwrite(self):
        if self._current_preset is None:
            self._show_notification(
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
        self._show_notification(f'✅ Updated: "{preset.name}"', timeout=3)

    def action_open_preset_browser(self):
        """Open the factory preset browser screen."""
        presets_data = get_factory_presets()
        screen = PresetBrowserScreen(
            presets_data,
            synth_engine=self.synth_engine,
            on_preset_selected=self._on_factory_preset_selected,
            on_cancel=self._on_preset_browser_cancel,
        )
        # Push screen onto the stack
        self.app.push_screen(screen)

    def _on_factory_preset_selected(self, category_id: str, preset_name: str, preset_data: dict):
        """Callback when a factory preset is selected from the browser.

        Factory presets are applied directly WITHOUT saving to preset manager.
        The user must press S to save it as a favorite (user preset).
        """
        if preset_data is None:
            return

        # Ensure factory preset has all required parameters with sensible defaults
        preset_params = dict(preset_data)  # Copy the preset

        # Add missing parameters that _apply_params expects
        if "amp_level" not in preset_params:
            preset_params["amp_level"] = 0.8
        if "master_volume" not in preset_params:
            preset_params["master_volume"] = 0.8
        if "arp_gate" not in preset_params:
            preset_params["arp_gate"] = 0.5
        if "chorus_voices" not in preset_params:
            preset_params["chorus_voices"] = 4

        # Apply factory preset to synth engine directly (no save yet)
        self._apply_params(preset_params)

        # Mark as dirty and not from preset manager
        self._current_preset = None
        self._preset_index = -1
        self._dirty = True
        self._suggested_preset_name = f"User: {preset_name}"  # Suggest name for S key save

        self._update_preset_ui()

    def _on_preset_browser_cancel(self):
        """Callback when preset browser is cancelled."""
        pass

    def _load_preset_at_index(self, index: int):
        preset = self.preset_manager.get(index)
        if preset is None:
            return
        self._current_preset = preset
        params = self.preset_manager.extract_params(preset)
        self._apply_params(params)
        self._dirty = False
        self._suggested_preset_name = None  # Clear suggested name when loading a preset
        self.config_manager.set_last_preset(preset.filename)
        self._update_preset_ui()

    # ── Parameter helpers ────────────────────────────────────────

    def _apply_params(self, params: dict):
        self.waveform   = params.get("waveform",  self.waveform)
        self.octave     = params.get("octave",    self.octave)
        self.noise_level = params.get("noise_level", self.noise_level)
        self.amp_level  = params.get("amp_level", self.amp_level)
        self.cutoff        = params.get("cutoff",        self.cutoff)
        self.hpf_cutoff    = params.get("hpf_cutoff",    self.hpf_cutoff)
        self.resonance     = min(0.80, params.get("resonance",     self.resonance))
        self.hpf_resonance = min(0.85, params.get("hpf_resonance", self.hpf_resonance))
        self.key_tracking    = params.get("key_tracking",    self.key_tracking)
        self.filter_drive    = params.get("filter_drive",    self.filter_drive)
        self.filter_routing  = params.get("filter_routing",  self.filter_routing)
        # Snap key_tracking to nearest discrete step when loading from old presets
        steps = self._KEY_TRACKING_STEPS
        self.key_tracking = steps[min(range(len(steps)), key=lambda i: abs(steps[i] - self.key_tracking))]
        # Clamp EG times to safe minimums — legacy presets may have sub-threshold values
        self.attack      = max(0.008, params.get("attack",      self.attack))
        self.decay       = max(0.005, params.get("decay",       self.decay))
        self.sustain     = params.get("sustain",   self.sustain)
        self.release     = max(0.008, params.get("release",     self.release))
        # Filter EG — same floor policy
        self.feg_attack  = max(0.008, params.get("feg_attack",  self.feg_attack))
        self.feg_decay   = max(0.005, params.get("feg_decay",   self.feg_decay))
        self.feg_sustain = params.get("feg_sustain", self.feg_sustain)
        self.feg_release = max(0.005, params.get("feg_release", self.feg_release))
        self.feg_amount  = params.get("feg_amount",  self.feg_amount)
        # LFO
        self.lfo_freq   = params.get("lfo_freq",   self.lfo_freq)
        self.lfo_depth  = params.get("lfo_depth",  self.lfo_depth)
        self.lfo_shape  = params.get("lfo_shape",  self.lfo_shape)
        self.lfo_target = params.get("lfo_target", self.lfo_target)
        # FX Delay
        self.delay_time     = params.get("delay_time",     self.delay_time)
        self.delay_feedback = params.get("delay_feedback", self.delay_feedback)
        self.delay_mix      = params.get("delay_mix",      self.delay_mix)
        # Chorus
        self.chorus_rate   = params.get("chorus_rate",   self.chorus_rate)
        self.chorus_depth  = params.get("chorus_depth",  self.chorus_depth)
        self.chorus_mix    = params.get("chorus_mix",    self.chorus_mix)
        self.chorus_voices = params.get("chorus_voices", self.chorus_voices)
        # Arpeggio (BPM from config_manager, not preset)
        self.arp_enabled = params.get("arp_enabled", self.arp_enabled)
        self.arp_mode    = params.get("arp_mode",    self.arp_mode)
        self.arp_gate    = params.get("arp_gate",    self.arp_gate)
        self.arp_range   = params.get("arp_range",   self.arp_range)
        # Voice Type
        self.voice_type  = params.get("voice_type",  self.voice_type)
        self._push_params_to_engine()
        self._refresh_all_displays()

    def _push_params_to_engine(self):
        self.synth_engine.update_parameters(
            waveform=self.waveform,
            octave=self.octave,
            noise_level=self.noise_level,
            amp_level=self.amp_level,
            master_volume=self.master_volume,
            cutoff=self.cutoff,
            hpf_cutoff=self.hpf_cutoff,
            resonance=self.resonance,
            hpf_resonance=self.hpf_resonance,
            key_tracking=self.key_tracking,
            filter_drive=self.filter_drive,
            filter_routing=self.filter_routing,
            attack=self.attack,
            decay=self.decay,
            sustain=self.sustain,
            release=self.release,
            feg_attack=self.feg_attack,
            feg_decay=self.feg_decay,
            feg_sustain=self.feg_sustain,
            feg_release=self.feg_release,
            feg_amount=self.feg_amount,
            # LFO
            lfo_freq=self.lfo_freq,
            lfo_depth=self.lfo_depth,
            lfo_shape=self.lfo_shape,
            lfo_target=self.lfo_target,
            # FX Delay
            delay_time=self.delay_time,
            delay_feedback=self.delay_feedback,
            delay_mix=self.delay_mix,
            # Chorus
            chorus_rate=self.chorus_rate,
            chorus_depth=self.chorus_depth,
            chorus_mix=self.chorus_mix,
            chorus_voices=self.chorus_voices,
            # Arpeggio
            arp_bpm=self.arp_bpm,
            arp_enabled=self.arp_enabled,
            arp_mode=self.arp_mode,
            arp_gate=self.arp_gate,
            arp_range=self.arp_range,
            # Voice Type
            voice_type=self.voice_type,
        )

    def _current_params(self) -> dict:
        return {
            "waveform":        self.waveform,
            "octave":          self.octave,
            "noise_level":     self.noise_level,
            "amp_level":       self.amp_level,
            "master_volume":   self.master_volume,
            "cutoff":          self.cutoff,
            "hpf_cutoff":      self.hpf_cutoff,
            "resonance":       self.resonance,
            "hpf_resonance":   self.hpf_resonance,
            "key_tracking":    self.key_tracking,
            "filter_drive":    self.filter_drive,
            "filter_routing":  self.filter_routing,
            "attack":          self.attack,
            "decay":           self.decay,
            "sustain":         self.sustain,
            "release":         self.release,
            "feg_attack":      self.feg_attack,
            "feg_decay":       self.feg_decay,
            "feg_sustain":     self.feg_sustain,
            "feg_release":     self.feg_release,
            "feg_amount":      self.feg_amount,
            # LFO
            "lfo_freq":        self.lfo_freq,
            "lfo_depth":       self.lfo_depth,
            "lfo_shape":       self.lfo_shape,
            "lfo_target":      self.lfo_target,
            # FX Delay
            "delay_time":      self.delay_time,
            "delay_feedback":  self.delay_feedback,
            "delay_mix":       self.delay_mix,
            # Chorus
            "chorus_rate":     self.chorus_rate,
            "chorus_depth":    self.chorus_depth,
            "chorus_mix":      self.chorus_mix,
            "chorus_voices":   self.chorus_voices,
            # Arpeggio (BPM excluded — lives in config_manager)
            "arp_enabled":     self.arp_enabled,
            "arp_mode":        self.arp_mode,
            "arp_gate":        self.arp_gate,
            "arp_range":       self.arp_range,
            # Voice Type
            "voice_type":      self.voice_type,
        }

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self._update_preset_ui()

    def _autosave_state(self):
        self.config_manager.set_synth_state(self._current_params())

    def _show_randomized_indicator(self, duration: float = 1.5):
        """Show 🎲 Randomized! indicator in preset bar, then hide it."""
        self._randomized_just_now = True
        self._update_preset_ui()
        self.set_timer(duration, self._hide_randomized_indicator)

    def _hide_randomized_indicator(self):
        """Hide the randomized indicator and refresh preset bar."""
        self._randomized_just_now = False
        self._update_preset_ui()

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

    def action_adjust_volume(self, direction: str = "up"):
        if self._focused():
            return
        self._do_adjust_volume(direction)

    # ── Init patch ──────────────────────────────────────────────────
    # A clean slate: pure sine, all filters wide open, no FX, no modulation.
    # This is what you get when you press "i" — the same role as "Init" on hardware.
    _INIT_PATCH = {
        "waveform":       "pure_sine",
        "noise_level":    0.0,
        "octave":         0,
        "filter_drive":   1.0,
        "filter_routing": "lp_hp",
        "hpf_cutoff":     20.0,
        "hpf_resonance":  0.0,
        "cutoff":         20000.0,
        "resonance":      0.0,
        "key_tracking":   0.5,
        "attack":         0.01,
        "decay":          0.2,
        "sustain":        0.7,
        "release":        0.3,
        "feg_attack":     0.01,
        "feg_decay":      0.3,
        "feg_sustain":    0.0,
        "feg_release":    0.3,
        "feg_amount":     0.0,
        "lfo_freq":       1.0,
        "lfo_depth":      0.0,
        "lfo_shape":      "sine",
        "lfo_target":     "all",
        "delay_time":     0.25,
        "delay_feedback": 0.3,
        "delay_mix":      0.0,
        "chorus_rate":    0.5,
        "chorus_depth":   0.0,
        "chorus_mix":     0.0,
        "chorus_voices":  2,
        "arp_enabled":    False,
        "arp_mode":       "up",
        "arp_gate":       0.5,
        "arp_range":      1,
        "voice_type":     "poly",
        "amp_level":      0.95,
    }

    def action_init_patch(self):
        """Reset to a clean init patch (pure sine, all filters open, no FX)."""
        self.synth_engine.midi_event_queue.put({'type': 'mute_gate'})
        self._apply_params(self._INIT_PATCH)
        self._current_preset = None
        self._preset_index   = -1
        self._dirty          = True
        self._suggested_preset_name = None
        self._update_preset_ui()
        self._autosave_state()
        self._show_notification("Init patch loaded", timeout=2)

    def action_reset_focused_param(self):
        """Reset the currently highlighted parameter to its init value.

        Only active in focus mode. Each param resets to the value in _INIT_PATCH
        so the result is consistent and predictable regardless of current state.
        """
        if not self._focused():
            return
        sec  = self._focus_section
        name = self._SECTION_PARAMS[sec][self._focus_param]
        ini  = self._INIT_PATCH

        def _push_and_refresh(param: str, display_attr: str, fmt_fn):
            self.synth_engine.update_parameters(**{param: getattr(self, param)})
            widget = getattr(self, display_attr, None)
            if widget:
                widget.update(fmt_fn())
            self._mark_dirty()
            self._autosave_state()

        if sec == "oscillator":
            if name == "Wave":
                self.waveform = ini["waveform"]
                self.synth_engine.update_parameters(waveform=self.waveform)
                if self.waveform_display: self.waveform_display.update(self._fmt_waveform())
                if self.waveform_shape_display: self.waveform_shape_display.update(self._fmt_waveform_shape())
            elif name == "Noise":
                self.noise_level = ini["noise_level"]
                _push_and_refresh("noise_level", "noise_display",
                                  lambda: self._fmt_knob(self.noise_level, 0.0, 1.0, f"{int(self.noise_level * 100)}%"))
            elif name == "Octave":
                self.octave = ini["octave"]
                _push_and_refresh("octave", "octave_display", self._fmt_octave)
            elif name == "Drive":
                self.filter_drive = ini["filter_drive"]
                _push_and_refresh("filter_drive", "filter_drive_display", self._fmt_filter_drive)

        elif sec == "filter":
            if name == "HPF Cut":
                self.hpf_cutoff = ini["hpf_cutoff"]
                _push_and_refresh("hpf_cutoff", "hpf_cutoff_display", self._fmt_hpf_cutoff)
            elif name == "HPF Pk":
                self.hpf_resonance = ini["hpf_resonance"]
                _push_and_refresh("hpf_resonance", "hpf_resonance_display", self._fmt_hpf_resonance)
            elif name == "LPF Cut":
                self.cutoff = ini["cutoff"]
                _push_and_refresh("cutoff", "cutoff_display", self._fmt_cutoff)
            elif name == "LPF Pk":
                self.resonance = ini["resonance"]
                _push_and_refresh("resonance", "resonance_display", self._fmt_resonance)
            elif name == "Route":
                self.filter_routing = ini["filter_routing"]
                _push_and_refresh("filter_routing", "filter_routing_display", self._fmt_filter_routing)

        elif sec == "amp_eg":
            if name == "Attack":
                self.attack = ini["attack"]
                _push_and_refresh("attack", "attack_display", lambda: self._fmt_time(self.attack))
            elif name == "Decay":
                self.decay = ini["decay"]
                _push_and_refresh("decay", "decay_display", lambda: self._fmt_time(self.decay))
            elif name == "Sustain":
                self.sustain = ini["sustain"]
                self.synth_engine.update_parameters(sustain=self.sustain)
                if self.sustain_display:
                    self.sustain_display.update(self._fmt_knob(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"))
                self._mark_dirty(); self._autosave_state()
            elif name == "Release":
                self.release = ini["release"]
                _push_and_refresh("release", "release_display", lambda: self._fmt_time(self.release))
            elif name == "KTrack":
                self.key_tracking = ini["key_tracking"]
                steps = self._KEY_TRACKING_STEPS
                self.key_tracking = steps[min(range(len(steps)), key=lambda i: abs(steps[i] - self.key_tracking))]
                self.synth_engine.update_parameters(key_tracking=self.key_tracking)
                if self.key_tracking_display: self.key_tracking_display.update(self._fmt_key_tracking())
                self._mark_dirty(); self._autosave_state()

        elif sec == "filter_eg":
            if name == "Atk":
                self.feg_attack = ini["feg_attack"]
                _push_and_refresh("feg_attack", "feg_attack_display", lambda: self._fmt_time(self.feg_attack))
            elif name == "Dcy":
                self.feg_decay = ini["feg_decay"]
                _push_and_refresh("feg_decay", "feg_decay_display", lambda: self._fmt_time(self.feg_decay))
            elif name == "Sus":
                self.feg_sustain = ini["feg_sustain"]
                self.synth_engine.update_parameters(feg_sustain=self.feg_sustain)
                if self.feg_sustain_display:
                    self.feg_sustain_display.update(self._fmt_knob(self.feg_sustain, 0.0, 1.0, f"{int(self.feg_sustain * 100)}%"))
                self._mark_dirty(); self._autosave_state()
            elif name == "Rel":
                self.feg_release = ini["feg_release"]
                _push_and_refresh("feg_release", "feg_release_display", lambda: self._fmt_time(self.feg_release))
            elif name == "Amount":
                self.feg_amount = ini["feg_amount"]
                _push_and_refresh("feg_amount", "feg_amount_display", self._fmt_feg_amount)

        elif sec == "lfo":
            if name == "Rate":
                self.lfo_freq = ini["lfo_freq"]
                _push_and_refresh("lfo_freq", "lfo_rate_display", self._fmt_lfo_rate)
            elif name == "Depth":
                self.lfo_depth = ini["lfo_depth"]
                self.synth_engine.update_parameters(lfo_depth=self.lfo_depth)
                if self.lfo_depth_display:
                    self.lfo_depth_display.update(self._fmt_knob(self.lfo_depth, 0.0, 1.0, f"{int(self.lfo_depth * 100)}%"))
                self._mark_dirty(); self._autosave_state()
            elif name == "Shape":
                self.lfo_shape = ini["lfo_shape"]
                _push_and_refresh("lfo_shape", "lfo_shape_display", self._fmt_lfo_shape)
            elif name == "Target":
                self.lfo_target = ini["lfo_target"]
                _push_and_refresh("lfo_target", "lfo_target_display", self._fmt_lfo_target)

        elif sec == "chorus":
            if name == "Rate":
                self.chorus_rate = ini["chorus_rate"]
                _push_and_refresh("chorus_rate", "chorus_rate_display", self._fmt_chorus_rate)
            elif name == "Depth":
                self.chorus_depth = ini["chorus_depth"]
                self.synth_engine.update_parameters(chorus_depth=self.chorus_depth)
                if self.chorus_depth_display:
                    self.chorus_depth_display.update(self._fmt_knob(self.chorus_depth, 0.0, 1.0, f"{int(self.chorus_depth * 100)}%"))
                self._mark_dirty(); self._autosave_state()
            elif name == "Mix":
                self.chorus_mix = ini["chorus_mix"]
                self.synth_engine.update_parameters(chorus_mix=self.chorus_mix)
                if self.chorus_mix_display:
                    self.chorus_mix_display.update(self._fmt_knob(self.chorus_mix, 0.0, 1.0, f"{int(self.chorus_mix * 100)}%"))
                self._mark_dirty(); self._autosave_state()
            elif name == "Voices":
                self.chorus_voices = ini["chorus_voices"]
                _push_and_refresh("chorus_voices", "chorus_voices_display", self._fmt_chorus_voices)

        elif sec == "fx":
            if name == "Delay Time":
                self.delay_time = ini["delay_time"]
                _push_and_refresh("delay_time", "delay_time_display", self._fmt_delay_time)
            elif name == "Delay Fdbk":
                self.delay_feedback = ini["delay_feedback"]
                self.synth_engine.update_parameters(delay_feedback=self.delay_feedback)
                if self.delay_feedback_display:
                    self.delay_feedback_display.update(self._fmt_knob(self.delay_feedback, 0.0, 0.9, f"{int(self.delay_feedback * 100)}%"))
                self._mark_dirty(); self._autosave_state()
            elif name == "Delay Mix":
                self.delay_mix = ini["delay_mix"]
                self.synth_engine.update_parameters(delay_mix=self.delay_mix)
                if self.delay_mix_display:
                    self.delay_mix_display.update(self._fmt_knob(self.delay_mix, 0.0, 1.0, f"{int(self.delay_mix * 100)}%"))
                self._mark_dirty(); self._autosave_state()

        elif sec == "arpeggio":
            if name == "Mode":
                self.arp_mode = ini["arp_mode"]
                _push_and_refresh("arp_mode", "arp_mode_display", self._fmt_arp_mode)
            elif name == "Gate":
                self.arp_gate = ini["arp_gate"]
                self.synth_engine.update_parameters(arp_gate=self.arp_gate)
                if self.arp_gate_display:
                    self.arp_gate_display.update(self._fmt_knob(self.arp_gate, 0.05, 1.0, f"{int(self.arp_gate * 100)}%"))
                self._mark_dirty(); self._autosave_state()
            elif name == "Range":
                self.arp_range = ini["arp_range"]
                _push_and_refresh("arp_range", "arp_range_display", self._fmt_arp_range)
            elif name == "ON/OFF":
                self.arp_enabled = ini["arp_enabled"]
                self.synth_engine.update_parameters(arp_enabled=self.arp_enabled)
                if self.arp_enabled_display:
                    self.arp_enabled_display.update(self._fmt_bool_toggle(self.arp_enabled, "ARP ON", "ARP OFF"))
                self._mark_dirty(); self._autosave_state()

        elif sec == "mixer":
            if name == "Voice Type":
                self.voice_type = ini["voice_type"]
                _push_and_refresh("voice_type", "voice_type_display", self._fmt_voice_type)
            elif name == "Amp":
                self.amp_level = ini["amp_level"]
                self.synth_engine.update_parameters(amp_level=self.amp_level)
                if self.amp_display:
                    self.amp_display.update(self._fmt_knob(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%"))
                self._mark_dirty(); self._autosave_state()

        self._show_notification(f"{name} → init", timeout=1)

    def action_panic(self):
        self.synth_engine.all_notes_off()
        self._show_notification("🛑 All notes off (Panic)", severity="warning", timeout=2)

    def action_randomize(self):
        """Roll the dice — generate musically useful random synth parameters."""
        self.waveform = random.choice(["pure_sine", "sine", "square", "sawtooth", "triangle"])
        self.octave = random.choices([-2, -1, 0, 1, 2], weights=[1, 2, 4, 2, 1])[0]
        self.amp_level = 0.95  # Always set to 95% (not randomized)
        self.cutoff = round(10 ** random.uniform(math.log10(200), math.log10(18000)), 1)
        self.hpf_cutoff = round(10 ** random.uniform(math.log10(20), math.log10(800)), 1)
        self.resonance = round(random.choices(
            [random.uniform(0.0, 0.3), random.uniform(0.3, 0.65), random.uniform(0.65, 0.9)],
            weights=[50, 35, 15]
        )[0], 2)
        self.hpf_resonance = round(random.choices(
            [0.0, random.uniform(0.0, 0.4), random.uniform(0.4, 0.8)],
            weights=[60, 30, 10]
        )[0], 2)
        self.voice_type = random.choice(["mono", "poly", "unison"])
        self.attack = round(10 ** random.uniform(math.log10(0.008), math.log10(2.0)), 4)
        self.decay = round(10 ** random.uniform(math.log10(0.005), math.log10(2.0)), 4)
        self.sustain = round(random.choices(
            [random.uniform(0.0, 0.3), random.uniform(0.3, 0.7), random.uniform(0.7, 1.0)],
            weights=[25, 35, 40]
        )[0], 2)
        self.release = round(10 ** random.uniform(math.log10(0.008), math.log10(3.0)), 4)
        self.intensity = round(random.uniform(0.40, 1.0), 2)

        # Randomize Filter EG amount only; timing params stay at defaults for musicality
        self.feg_amount = round(random.uniform(0.5, 1.0), 2)
        self.synth_engine.update_parameters(feg_amount=self.feg_amount)

        # Enqueue mute gate BEFORE the param update so the engine fades out
        # before the new waveform/octave/envelope params take effect — this
        # prevents a click on any currently held notes.  Both events are drained
        # in the same _process_midi_events() call, so the fade-in that follows
        # plays back with the new params already active.
        self.synth_engine.midi_event_queue.put({'type': 'mute_gate'})
        self._push_params_to_engine()
        self._refresh_all_displays()

        # Generate suggested name for the randomized parameters
        # (user can save manually if they want)
        self._suggested_preset_name = self.preset_manager._unique_musical_name()

        # Mark as unsaved since parameters have changed
        self._current_preset = None
        self._preset_index = -1
        self._dirty = True

        self._update_preset_ui()
        self._autosave_state()

        # Show 🎲 Randomized! indicator in preset bar (avoids audio thread blocking)
        self._show_randomized_indicator()

    def action_randomize_focused(self):
        """Shift+Minus — randomize only the currently highlighted parameter.

        Each parameter type picks a value from a musically useful range
        using the same distributions as the full randomize action.
        Only active in focus mode — silently ignored when unfocused.
        """
        if not self._focused():
            return
        sec   = self._focus_section
        pidx  = self._focus_param
        params = self._SECTION_PARAMS.get(sec, [])
        if not params or pidx >= len(params):
            return
        name = params[pidx]

        # ── Oscillator ────────────────────────────────────────────
        if sec == "oscillator":
            if name == "Wave":
                self.waveform = random.choice(["pure_sine", "sine", "square", "sawtooth", "triangle"])
                self.synth_engine.update_parameters(waveform=self.waveform)
                if self.waveform_display: self.waveform_display.update(self._fmt_waveform())
                if self.waveform_shape_display: self.waveform_shape_display.update(self._fmt_waveform_shape())
            elif name == "Octave":
                self.octave = random.choices([-2, -1, 0, 1, 2], weights=[1, 2, 4, 2, 1])[0]
                self.synth_engine.update_parameters(octave=self.octave)
                if self.octave_display: self.octave_display.update(self._fmt_octave())
            elif name == "Drive":
                pass  # Drive excluded from randomization — user sets this manually
        # ── Filter ────────────────────────────────────────────────
        elif sec == "filter":
            if name == "HPF Cut":
                self.hpf_cutoff = round(10 ** random.uniform(math.log10(20), math.log10(3000)), 1)
                self.synth_engine.update_parameters(hpf_cutoff=self.hpf_cutoff)
                if self.hpf_cutoff_display: self.hpf_cutoff_display.update(self._fmt_hpf_cutoff())
            elif name == "HPF Pk":
                self.hpf_resonance = round(random.uniform(0.0, 0.8), 2)
                self.synth_engine.update_parameters(hpf_resonance=self.hpf_resonance)
                if self.hpf_resonance_display: self.hpf_resonance_display.update(self._fmt_hpf_resonance())
            elif name == "LPF Cut":
                self.cutoff = round(10 ** random.uniform(math.log10(200), math.log10(18000)), 1)
                self.synth_engine.update_parameters(cutoff=self.cutoff)
                if self.cutoff_display: self.cutoff_display.update(self._fmt_cutoff())
            elif name == "LPF Pk":
                self.resonance = round(random.choices(
                    [random.uniform(0.0, 0.3), random.uniform(0.3, 0.65), random.uniform(0.65, 0.9)],
                    weights=[50, 35, 15])[0], 2)
                self.synth_engine.update_parameters(resonance=self.resonance)
                if self.resonance_display: self.resonance_display.update(self._fmt_resonance())
            elif name == "Route":
                pass  # Filter routing excluded from randomization — user sets this manually
        # ── Amp EG ────────────────────────────────────────────────
        elif sec == "amp_eg":
            if name == "Attack":
                self.attack = round(10 ** random.uniform(math.log10(0.008), math.log10(2.0)), 4)
                self.synth_engine.update_parameters(attack=self.attack)
                if self.attack_display: self.attack_display.update(self._fmt_time(self.attack))
            elif name == "Decay":
                self.decay = round(10 ** random.uniform(math.log10(0.005), math.log10(2.0)), 4)
                self.synth_engine.update_parameters(decay=self.decay)
                if self.decay_display: self.decay_display.update(self._fmt_time(self.decay))
            elif name == "Sustain":
                self.sustain = round(random.choices(
                    [random.uniform(0.0, 0.3), random.uniform(0.3, 0.7), random.uniform(0.7, 1.0)],
                    weights=[25, 35, 40])[0], 2)
                self.synth_engine.update_parameters(sustain=self.sustain)
                if self.sustain_display: self.sustain_display.update(self._fmt_knob(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"))
            elif name == "Release":
                self.release = round(10 ** random.uniform(math.log10(0.008), math.log10(3.0)), 4)
                self.synth_engine.update_parameters(release=self.release)
                if self.release_display: self.release_display.update(self._fmt_time(self.release))
            elif name == "KTrack":
                pass  # Key Tracking excluded from randomization — user sets this manually
        # ── Filter EG ─────────────────────────────────────────────
        elif sec == "filter_eg":
            label = self._SECTION_PARAMS["filter_eg"][self._focus_param]
            if label == "Atk":
                self.feg_attack = round(random.uniform(0.008, 2.0), 3)
                self.synth_engine.update_parameters(feg_attack=self.feg_attack)
                if self.feg_attack_display: self.feg_attack_display.update(self._fmt_time(self.feg_attack))
            elif label == "Dcy":
                self.feg_decay = round(random.uniform(0.005, 2.0), 3)
                self.synth_engine.update_parameters(feg_decay=self.feg_decay)
                if self.feg_decay_display: self.feg_decay_display.update(self._fmt_time(self.feg_decay))
            elif label == "Sus":
                self.feg_sustain = round(random.uniform(0.0, 1.0), 2)
                self.synth_engine.update_parameters(feg_sustain=self.feg_sustain)
                if self.feg_sustain_display: self.feg_sustain_display.update(self._fmt_knob(self.feg_sustain, 0.0, 1.0, f"{int(self.feg_sustain * 100)}%"))
            elif label == "Rel":
                self.feg_release = round(random.uniform(0.01, 2.0), 3)
                self.synth_engine.update_parameters(feg_release=self.feg_release)
                if self.feg_release_display: self.feg_release_display.update(self._fmt_time(self.feg_release))
            elif label == "Amount":
                self.feg_amount = round(random.uniform(0.5, 1.0), 2)
                self.synth_engine.update_parameters(feg_amount=self.feg_amount)
                if self.feg_amount_display: self.feg_amount_display.update(self._fmt_feg_amount())
            self._mark_dirty(); self._autosave_state()
        # ── LFO ───────────────────────────────────────────────────
        elif sec == "lfo":
            if name == "Rate":
                self.lfo_freq = round(10 ** random.uniform(math.log10(0.05), math.log10(20.0)), 3)
                self.synth_engine.update_parameters(lfo_freq=self.lfo_freq)
                if self.lfo_rate_display: self.lfo_rate_display.update(self._fmt_lfo_rate())
            elif name == "Depth":
                self.lfo_depth = round(random.uniform(0.0, 1.0), 2)
                self.synth_engine.update_parameters(lfo_depth=self.lfo_depth)
                if self.lfo_depth_display: self.lfo_depth_display.update(self._fmt_knob(self.lfo_depth, 0.0, 1.0, f"{int(self.lfo_depth * 100)}%"))
            elif name == "Shape":
                self.lfo_shape = random.choice(["sine", "triangle", "square", "sample_hold"])
                self.synth_engine.update_parameters(lfo_shape=self.lfo_shape)
                if self.lfo_shape_display: self.lfo_shape_display.update(self._fmt_lfo_shape())
            elif name == "Target":
                self.lfo_target = random.choice(["all", "vco", "vcf", "vca"])
                self.synth_engine.update_parameters(lfo_target=self.lfo_target)
                if self.lfo_target_display: self.lfo_target_display.update(self._fmt_lfo_target())
        # ── Chorus ────────────────────────────────────────────────
        elif sec == "chorus":
            if name == "Rate":
                self.chorus_rate = round(10 ** random.uniform(math.log10(0.1), math.log10(10.0)), 2)
                self.synth_engine.update_parameters(chorus_rate=self.chorus_rate)
                if self.chorus_rate_display: self.chorus_rate_display.update(self._fmt_chorus_rate())
            elif name == "Depth":
                self.chorus_depth = round(random.uniform(0.0, 1.0), 2)
                self.synth_engine.update_parameters(chorus_depth=self.chorus_depth)
                if self.chorus_depth_display: self.chorus_depth_display.update(self._fmt_knob(self.chorus_depth, 0.0, 1.0, f"{int(self.chorus_depth * 100)}%"))
            elif name == "Mix":
                self.chorus_mix = round(random.uniform(0.0, 0.8), 2)
                self.synth_engine.update_parameters(chorus_mix=self.chorus_mix)
                if self.chorus_mix_display: self.chorus_mix_display.update(self._fmt_knob(self.chorus_mix, 0.0, 1.0, f"{int(self.chorus_mix * 100)}%"))
            elif name == "Voices":
                self.chorus_voices = random.randint(1, 4)
                self.synth_engine.update_parameters(chorus_voices=self.chorus_voices)
                if self.chorus_voices_display: self.chorus_voices_display.update(self._fmt_chorus_voices())
        # ── FX Delay ──────────────────────────────────────────────
        elif sec == "fx":
            if name == "Delay Time":
                self.delay_time = round(random.uniform(0.05, 2.0), 3)
                self.synth_engine.update_parameters(delay_time=self.delay_time)
                if self.delay_time_display: self.delay_time_display.update(self._fmt_delay_time())
            elif name == "Delay Fdbk":
                self.delay_feedback = round(random.uniform(0.0, 0.85), 2)
                self.synth_engine.update_parameters(delay_feedback=self.delay_feedback)
                if self.delay_feedback_display: self.delay_feedback_display.update(self._fmt_knob(self.delay_feedback, 0.0, 0.9, f"{int(self.delay_feedback * 100)}%"))
            elif name == "Delay Mix":
                self.delay_mix = round(random.uniform(0.0, 0.8), 2)
                self.synth_engine.update_parameters(delay_mix=self.delay_mix)
                if self.delay_mix_display: self.delay_mix_display.update(self._fmt_knob(self.delay_mix, 0.0, 1.0, f"{int(self.delay_mix * 100)}%"))
            # Rev Size is a placeholder — no-op
        # ── Arpeggio ──────────────────────────────────────────────
        elif sec == "arpeggio":
            if name == "Mode":
                self.arp_mode = random.choice(["up", "down", "up_down", "random"])
                self.synth_engine.update_parameters(arp_mode=self.arp_mode)
                if self.arp_mode_display: self.arp_mode_display.update(self._fmt_arp_mode())
            elif name == "BPM":
                self.arp_bpm = float(random.randrange(60, 181, 5))
                self.config_manager.set_bpm(int(self.arp_bpm))
                self.synth_engine.update_parameters(arp_bpm=self.arp_bpm)
                if self.arp_bpm_display: self.arp_bpm_display.update(self._fmt_knob(self.arp_bpm, 50.0, 300.0, f"{int(self.arp_bpm)} BPM"))
            elif name == "Gate":
                self.arp_gate = round(random.uniform(0.1, 0.95), 2)
                self.synth_engine.update_parameters(arp_gate=self.arp_gate)
                if self.arp_gate_display: self.arp_gate_display.update(self._fmt_knob(self.arp_gate, 0.05, 1.0, f"{int(self.arp_gate * 100)}%"))
            elif name == "Range":
                self.arp_range = random.randint(1, 4)
                self.synth_engine.update_parameters(arp_range=self.arp_range)
                if self.arp_range_display: self.arp_range_display.update(self._fmt_arp_range())
            elif name == "ON/OFF":
                self._do_toggle_arp_enabled()   # toggle is more useful than random bool
        # ── Mixer ─────────────────────────────────────────────────
        elif sec == "mixer":
            if name == "Voice Type":
                self.voice_type = random.choice(["mono", "poly", "unison"])
                self.synth_engine.update_parameters(voice_type=self.voice_type)
                if self.voice_type_display:
                    self.voice_type_display.update(self._fmt_voice_type())
            elif name == "Amp":
                # Amp is always 95% — not randomized
                pass
            elif name == "Master Vol":
                self.master_volume = round(random.uniform(0.5, 1.0), 2)
                self.synth_engine.update_parameters(master_volume=self.master_volume)
                if self.master_volume_display: self.master_volume_display.update(self._fmt_knob(self.master_volume, 0.0, 1.0, f"{int(self.master_volume * 100)}%"))

        self._mark_dirty()
        self._autosave_state()
        self._show_notification(f"🎲 {name} randomized!", timeout=1)

    # ── Display refresh ──────────────────────────────────────────

    def _refresh_all_displays(self):
        if self.waveform_display: self.waveform_display.update(self._fmt_waveform())
        if self.waveform_shape_display: self.waveform_shape_display.update(self._fmt_waveform_shape())
        if self.octave_display: self.octave_display.update(self._fmt_octave())
        if self.hpf_cutoff_display: self.hpf_cutoff_display.update(self._fmt_hpf_cutoff())
        if self.hpf_resonance_display: self.hpf_resonance_display.update(self._fmt_hpf_resonance())
        if self.cutoff_display: self.cutoff_display.update(self._fmt_cutoff())
        if self.resonance_display: self.resonance_display.update(self._fmt_resonance())
        if self.key_tracking_display: self.key_tracking_display.update(self._fmt_key_tracking())
        if self.filter_drive_display: self.filter_drive_display.update(self._fmt_filter_drive())
        if self.filter_routing_display: self.filter_routing_display.update(self._fmt_filter_routing())
        if self.attack_display: self.attack_display.update(self._fmt_time(self.attack))
        if self.decay_display: self.decay_display.update(self._fmt_time(self.decay))
        if self.sustain_display: self.sustain_display.update(self._fmt_knob(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"))
        if self.release_display: self.release_display.update(self._fmt_time(self.release))
        # Filter EG
        if self.feg_attack_display:  self.feg_attack_display.update(self._fmt_time(self.feg_attack))
        if self.feg_decay_display:   self.feg_decay_display.update(self._fmt_time(self.feg_decay))
        if self.feg_sustain_display: self.feg_sustain_display.update(self._fmt_knob(self.feg_sustain, 0.0, 1.0, f"{int(self.feg_sustain * 100)}%"))
        if self.feg_release_display: self.feg_release_display.update(self._fmt_time(self.feg_release))
        if self.feg_amount_display:  self.feg_amount_display.update(self._fmt_feg_amount())
        # Mixer
        if self.voice_type_display: self.voice_type_display.update(self._fmt_voice_type())
        if self.amp_display: self.amp_display.update(self._fmt_knob(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%"))
        if self.master_volume_display: self.master_volume_display.update(self._fmt_knob(self.master_volume, 0.0, 1.0, f"{int(self.master_volume * 100)}%"))
        # LFO
        if self.lfo_rate_display: self.lfo_rate_display.update(self._fmt_lfo_rate())
        if self.lfo_depth_display: self.lfo_depth_display.update(self._fmt_knob(self.lfo_depth, 0.0, 1.0, f"{int(self.lfo_depth * 100)}%"))
        if self.lfo_shape_display: self.lfo_shape_display.update(self._fmt_lfo_shape())
        if self.lfo_target_display: self.lfo_target_display.update(self._fmt_lfo_target())
        # Chorus
        if self.chorus_rate_display: self.chorus_rate_display.update(self._fmt_chorus_rate())
        if self.chorus_depth_display: self.chorus_depth_display.update(self._fmt_knob(self.chorus_depth, 0.0, 1.0, f"{int(self.chorus_depth * 100)}%"))
        if self.chorus_mix_display: self.chorus_mix_display.update(self._fmt_knob(self.chorus_mix, 0.0, 1.0, f"{int(self.chorus_mix * 100)}%"))
        if self.chorus_voices_display: self.chorus_voices_display.update(self._fmt_chorus_voices())
        # FX Delay
        if self.delay_time_display: self.delay_time_display.update(self._fmt_delay_time())
        if self.delay_feedback_display: self.delay_feedback_display.update(self._fmt_knob(self.delay_feedback, 0.0, 0.9, f"{int(self.delay_feedback * 100)}%"))
        if self.delay_mix_display: self.delay_mix_display.update(self._fmt_knob(self.delay_mix, 0.0, 1.0, f"{int(self.delay_mix * 100)}%"))
        # Arpeggio
        if self.arp_mode_display: self.arp_mode_display.update(self._fmt_arp_mode())
        if self.arp_bpm_display: self.arp_bpm_display.update(self._fmt_knob(self.arp_bpm, 50.0, 300.0, f"{int(self.arp_bpm)} BPM"))
        if self.arp_gate_display: self.arp_gate_display.update(self._fmt_knob(self.arp_gate, 0.05, 1.0, f"{int(self.arp_gate * 100)}%"))
        if self.arp_range_display: self.arp_range_display.update(self._fmt_arp_range())
        if self.arp_enabled_display: self.arp_enabled_display.update(self._fmt_bool_toggle(self.arp_enabled, "ARP ON", "ARP OFF"))

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
        # Log-scale display: min=5ms (lowest of all EG time minimums), max=5s
        log_t = math.log10(max(0.005, t))
        log_min = math.log10(0.005)
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
        return self._fmt_knob(self.resonance / 0.80, 0.0, 1.0, f"{int(self.resonance * 100)}%")

    def _fmt_hpf_cutoff(self) -> str:
        log_c = math.log10(max(20.0, self.hpf_cutoff))
        log_min = math.log10(20.0)
        log_max = math.log10(4000.0)
        norm = (log_c - log_min) / (log_max - log_min)
        label = f"{self.hpf_cutoff / 1000:.2f}kHz" if self.hpf_cutoff >= 1000 else f"{self.hpf_cutoff:.0f}Hz"
        return self._fmt_knob(norm, 0.0, 1.0, label)

    def _fmt_hpf_resonance(self) -> str:
        return self._fmt_knob(self.hpf_resonance / 0.85, 0.0, 1.0, f"{int(self.hpf_resonance * 100)}%")

    def _fmt_key_tracking(self) -> str:
        """Five-mode selector display for key tracking: 0%·25%·50%·75%·100%."""
        steps = self._KEY_TRACKING_STEPS
        labels = ["0%", "25%", "50%", "75%", "100%"]
        # Find current step
        idx = min(range(len(steps)), key=lambda i: abs(steps[i] - self.key_tracking))
        parts = []
        for i, lbl in enumerate(labels):
            if i == idx:
                parts.append(f"[bold #00ff00 reverse]{lbl}[/]")
            else:
                parts.append(f"[#446644]{lbl}[/]")
        line  = "·".join(parts)
        plain = "·".join(labels)
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

    def _fmt_filter_drive(self) -> str:
        """Filter drive knob display (0.5x–8.0x)."""
        return self._fmt_knob(self.filter_drive, 0.5, 8.0, f"{self.filter_drive:.1f}x")

    _FILTER_ROUTING_LABELS = {
        "lp_hp":    "HP+LP",
        "bp_lp":    "BP+LP",
        "notch_lp": "NT+LP",
        "lp_lp":    "LP+LP",
    }

    def _fmt_filter_routing(self) -> str:
        """Four-mode selector display for filter routing."""
        opts = self._FILTER_ROUTING_OPTIONS
        labels = [self._FILTER_ROUTING_LABELS[o] for o in opts]
        idx = opts.index(self.filter_routing) if self.filter_routing in opts else 0
        parts = []
        for i, lbl in enumerate(labels):
            if i == idx:
                parts.append(f"[bold #00ff00 reverse]{lbl}[/]")
            else:
                parts.append(f"[#446644]{lbl}[/]")
        line  = "·".join(parts)
        plain = "·".join(labels)
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

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

    # ── LFO formatters ────────────────────────────────────────────

    def _fmt_lfo_rate(self) -> str:
        # Log-scale knob: 0.05 Hz → 20 Hz
        log_r = math.log10(max(0.05, self.lfo_freq))
        log_min = math.log10(0.05)
        log_max = math.log10(20.0)
        norm = (log_r - log_min) / (log_max - log_min)
        label = f"{self.lfo_freq:.2f} Hz"
        return self._fmt_knob(norm, 0.0, 1.0, label)

    def _fmt_lfo_shape(self) -> str:
        entries = [("sine", "SIN"), ("triangle", "TRI"), ("square", "SQR"), ("sample_hold", "S&H")]
        parts = []
        for key, tag in entries:
            if self.lfo_shape == key:
                parts.append(f"[bold #00ff00 reverse]{tag}[/]")
            else:
                parts.append(f"[#446644]{tag}[/]")
        line  = " ".join(parts)
        plain = " ".join(tag for _, tag in entries)
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

    def _fmt_lfo_target(self) -> str:
        entries = [("all", "ALL"), ("vco", "VCO"), ("vcf", "VCF"), ("vca", "VCA")]
        parts = []
        for key, tag in entries:
            if self.lfo_target == key:
                parts.append(f"[bold #00ff00 reverse]{tag}[/]")
            else:
                parts.append(f"[#446644]{tag}[/]")
        line  = " ".join(parts)
        plain = " ".join(tag for _, tag in entries)
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

    # ── Chorus formatters ──────────────────────────────────────────

    def _fmt_chorus_rate(self) -> str:
        log_r = math.log10(max(0.1, self.chorus_rate))
        log_min = math.log10(0.1)
        log_max = math.log10(10.0)
        norm = (log_r - log_min) / (log_max - log_min)
        return self._fmt_knob(norm, 0.0, 1.0, f"{self.chorus_rate:.2f} Hz")

    def _fmt_chorus_voices(self) -> str:
        options = ["1", "2", "3", "4"]
        parts = []
        for i, opt in enumerate(options):
            if i + 1 == self.chorus_voices:
                parts.append(f"[bold #00ff00 reverse]{opt}[/]")
            else:
                parts.append(f"[#446644]{opt}[/]")
        line  = " ".join(parts)
        plain = " ".join(options)
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

    # ── FX Delay formatters ────────────────────────────────────────

    def _fmt_delay_time(self) -> str:
        norm = (self.delay_time - 0.05) / (2.0 - 0.05)
        ms   = int(self.delay_time * 1000)
        return self._fmt_knob(norm, 0.0, 1.0, f"{ms} ms")

    def _fmt_feg_amount(self) -> str:
        """Format feg_amount as +XX% or -XX% with knob bar."""
        pct = int(self.feg_amount * 100)
        sign = "+" if pct >= 0 else ""
        return self._fmt_knob(self.feg_amount, -1.0, 1.0, f"{sign}{pct}%")

    def _fmt_disabled_param(self, reason: str = "future") -> str:
        """Grey placeholder for params not yet implemented."""
        lbl   = f"— {reason} —"
        pad   = max(0, self._W - len(lbl))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}[dim #556655]{lbl}[/]{' ' * rp}[#00cc00]│[/]"

    # ── Arpeggio formatters ────────────────────────────────────────

    def _fmt_arp_mode(self) -> str:
        entries = [("up", "UP"), ("down", "DN"), ("up_down", "U+D"), ("random", "RND")]
        parts = []
        for key, tag in entries:
            if self.arp_mode == key:
                parts.append(f"[bold #00ff00 reverse]{tag}[/]")
            else:
                parts.append(f"[#446644]{tag}[/]")
        line  = " ".join(parts)
        plain = " ".join(tag for _, tag in entries)
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

    def _fmt_arp_range(self) -> str:
        options = ["1", "2", "3", "4"]
        parts = []
        for i, opt in enumerate(options):
            if i + 1 == self.arp_range:
                parts.append(f"[bold #00ff00 reverse]{opt}[/]")
            else:
                parts.append(f"[#446644]{opt}[/]")
        line  = " ".join(parts)
        plain = " ".join(options)
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

    def _fmt_bool_toggle(self, value: bool, label_on: str, label_off: str) -> str:
        """Green ON / dimmed OFF toggle display."""
        on_part  = f"[bold #00ff00 reverse]{label_on}[/]"  if value else f"[#446644]{label_on}[/]"
        off_part = f"[#446644]{label_off}[/]"              if value else f"[bold #ff6600 reverse]{label_off}[/]"
        line  = f"{on_part}  {off_part}"
        plain = f"{label_on}  {label_off}"
        pad   = max(0, self._W - len(plain))
        lp    = pad // 2
        rp    = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{line}{' ' * rp}[#00cc00]│[/]"

    def _fmt_voice_type(self) -> str:
        """Format voice type as radio button display: ●MONO ○POLY ○UNISON"""
        modes = ["MONO", "POLY", "UNISON"]
        mode_values = ["mono", "poly", "unison"]
        try:
            idx = mode_values.index(self.voice_type.lower())
        except (ValueError, AttributeError):
            idx = 1  # Default to POLY if invalid

        # Display as: ●MONO ○POLY ○UNISON (with selected one highlighted)
        display_parts = []
        for i, mode in enumerate(modes):
            if i == idx:
                display_parts.append(f"[bold #00ff00]●{mode}[/]")
            else:
                display_parts.append(f"[#666666]○{mode}[/]")

        display = " ".join(display_parts)
        # Calculate plain text for padding (without markup)
        plain = " ".join([f"●{m}" if i == idx else f"○{m}" for i, m in enumerate(modes)])
        pad = max(0, self._W - len(plain))
        lp = pad // 2
        rp = pad - lp
        return f"[#00cc00]│[/]{' ' * lp}{display}{' ' * rp}[#00cc00]│[/]"

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

    # ── Preset bar ────────────────────────────────────────────────

    def _fmt_preset_bar(self) -> str:
        total = self.preset_manager.count()
        randomized_indicator = " [bold #00ff00]🎲 Randomized![/]" if self._randomized_just_now else ""

        if self._current_preset and total:
            idx   = self._preset_index + 1
            dirty = " [bold yellow]✱[/]" if self._dirty else ""

            # Show origin icon: 👤 for user presets, 🏭 for built-in preset list
            origin_icon = "👤" if self._current_preset.origin == "user" else "🏭"

            return (
                f"[dim #00aa00]◄[/] {origin_icon} [bold #00ff00]{self._current_preset.name}[/]{dirty}"
                f"  [dim]({idx}/{total})[/]"
                f"  [dim #00aa00]►[/]{randomized_indicator}"
            )
        elif self._dirty and self._suggested_preset_name:
            # Show suggested name after randomization
            return f"[bold yellow]✱ {self._suggested_preset_name}[/]{randomized_indicator}"
        elif self._dirty:
            return f"[bold yellow]✱ unsaved[/]{randomized_indicator}"
        else:
            return "[dim]— no preset —[/]"
