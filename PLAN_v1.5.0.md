# Acordes v1.5.0 — Synth Module Expansion Plan
## LFO · Delay FX · Chorus · Arpeggiator

---

## Overview

Four modules will be wired in four independent phases. Each phase produces a working,
committable state and does not break anything in the previous phase.

**Delivery order (lowest-to-highest complexity):**

```
Phase 1 — LFO        (engine already 90% wired; add shape + target + depth UI)
Phase 2 — FX Delay   (ring buffer, post-mix, simple DSP)
Phase 3 — Chorus     (modulated taps, post-mix, stereo)
Phase 4 — Arpeggio   (audio-callback clock, shared BPM, note interception)
```

**Files touched per phase:**

| Phase | preset_manager.py | synth_engine.py | synth_mode.py | config_manager.py | metronome_mode.py | main.py |
|-------|:-----------------:|:---------------:|:-------------:|:-----------------:|:-----------------:|:-------:|
| 1 LFO | ✓ | ✓ | ✓ | — | — | — |
| 2 Delay | ✓ | ✓ | ✓ | — | — | — |
| 3 Chorus | ✓ | ✓ | ✓ | — | — | — |
| 4 Arp | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## Final Signal Flow (after all phases)

```
_process_midi_events()           ← arp note interception here
Arpeggiator clock                ← new: audio-callback driven step sequencer
_update_voice_frequencies()
Parameter smoothing
LFO generation                   ← upgraded: shape + per-target routing
Per-voice DSP loop               ← unchanged
  oscillator → filter → envelope × vca_lfo → onset ramp → DC blocker → pan
Stereo mix (mixed_l, mixed_r)
Chorus                           ← new: modulated delay taps, post-mix
FX Delay                         ← new: ring buffer, post-chorus
_filter_ramp                     ← unchanged
_mute_ramp                       ← unchanged
tanh → master_volume → int16
```

---

## Phase 1 — LFO (Full Shape + Target + Depth)

### What changes
The engine already has `lfo_freq`, `lfo_vco_mod`, `lfo_vcf_mod`, `lfo_vca_mod`, `lfo_phase`
fully wired with a sine wave. We add:
- **Shape** selector: SIN / TRI / S&H / SQR
- **Target** selector: VCO / VCF / VCA / ALL
- **Depth** knob: 0–100% (single master depth, routes to the correct target)
- All three old `lfo_*_mod` attrs kept as internal backing but computed dynamically each buffer.

### 1-A  `preset_manager.py`
Add after the four existing LFO keys (after `"lfo_vca_mod": 0.0`):
```python
"lfo_shape":  "sine",   # "sine" | "triangle" | "square" | "sample_hold"
"lfo_target": "all",    # "vco"  | "vcf"       | "vca"    | "all"
"lfo_depth":  0.0,      # 0.0–1.0  master depth
```

### 1-B  `synth_engine.py` — `__init__`
Add at top of file (module level, after existing imports):
```python
import random as _rnd
```
Add in `SynthEngine.__init__` after `self.lfo_phase = 0.0`:
```python
self.lfo_shape  = "sine"   # shape selector
self.lfo_target = "all"    # routing target
self.lfo_depth  = 0.0      # master depth 0–1
# S&H internal state
self._lfo_sh_value = 0.0   # held random sample value
```

### 1-C  `synth_engine.py` — `_audio_callback` LFO block
Replace the existing 5-line LFO block (the one that does `lfo_val = np.sin(self.lfo_phase)`)
with the following:
```python
# ── LFO — shape-aware single value per buffer ─────────────────────
lfo_phase_prev = self.lfo_phase
lfo_phase_inc  = 2 * np.pi * self.lfo_freq * frame_count / self.sample_rate
self.lfo_phase = (self.lfo_phase + lfo_phase_inc) % (2 * np.pi)

if self.lfo_shape == "triangle":
    t_norm  = lfo_phase_prev / (2 * np.pi)
    lfo_val = float(4.0 * abs(t_norm - 0.5) - 1.0)
elif self.lfo_shape == "square":
    lfo_val = 1.0 if lfo_phase_prev < np.pi else -1.0
elif self.lfo_shape == "sample_hold":
    # New random sample on every phase wrap (period crossing)
    if lfo_phase_prev > self.lfo_phase:   # wrapped — new period
        self._lfo_sh_value = _rnd.uniform(-1.0, 1.0)
    lfo_val = self._lfo_sh_value
else:  # "sine" (default)
    lfo_val = float(np.sin(lfo_phase_prev))

# Route depth to the correct target(s)
d = float(self.lfo_depth)
if self.lfo_target == "vco":
    vco_mod, vcf_mod, vca_mod = d, 0.0, 0.0
elif self.lfo_target == "vcf":
    vco_mod, vcf_mod, vca_mod = 0.0, d, 0.0
elif self.lfo_target == "vca":
    vco_mod, vcf_mod, vca_mod = 0.0, 0.0, d
else:  # "all"
    vco_mod = vcf_mod = vca_mod = d

vco_lfo = 1.0 + lfo_val * vco_mod * 0.05
vcf_lfo = 1.0 + lfo_val * vcf_mod * 0.5
vca_lfo = 1.0 + lfo_val * vca_mod * 0.3
```

### 1-D  `synth_mode.py`
**New instance vars** (in `__init__`, reading from `params`):
```python
self.lfo_freq   = params.get("lfo_freq",   1.0)
self.lfo_depth  = params.get("lfo_depth",  0.0)
self.lfo_shape  = params.get("lfo_shape",  "sine")
self.lfo_target = params.get("lfo_target", "all")
# widget refs
self.lfo_rate_display   = None
self.lfo_depth_display  = None
self.lfo_shape_display  = None
self.lfo_target_display = None
```

**Replace `compose()` LFO section** (currently has 4 hardcoded dummy Label lines) with:
```python
with Vertical(id="lfo-section"):
    hdr = Label(self._section_top("LFO", False), classes="section-label", id="hdr-lfo")
    self._section_header_ids["lfo"] = "hdr-lfo"
    yield hdr
    yield Label(self._row_label("Rate", ""), classes="control-label", id="lbl-lfo-0")
    self.lfo_rate_display = Label(self._fmt_lfo_rate(), classes="control-value", id="lfo-rate-display")
    yield self.lfo_rate_display
    yield Label(self._row_label("Depth", ""), classes="control-label", id="lbl-lfo-1")
    self.lfo_depth_display = Label(
        self._fmt_knob(self.lfo_depth, 0.0, 1.0, f"{int(self.lfo_depth*100)}%"),
        classes="control-value", id="lfo-depth-display")
    yield self.lfo_depth_display
    yield Label(self._row_sep(), classes="control-label")
    yield Label(self._row_label("Shape", ""), classes="control-label", id="lbl-lfo-2")
    self.lfo_shape_display = Label(self._fmt_lfo_shape(), classes="control-value", id="lfo-shape-display")
    yield self.lfo_shape_display
    yield Label(self._row_label("Target", ""), classes="control-label", id="lbl-lfo-3")
    self.lfo_target_display = Label(self._fmt_lfo_target(), classes="control-value", id="lfo-target-display")
    yield self.lfo_target_display
    yield Label(self._section_bottom(), classes="section-label")
```

**New formatter methods** (following existing `_fmt_filter_mode` pattern):
```python
def _fmt_lfo_rate(self) -> str:
    import math
    norm  = (math.log10(max(0.1, self.lfo_freq)) - math.log10(0.1)) / (math.log10(20.0) - math.log10(0.1))
    return self._fmt_knob(norm, 0.0, 1.0, f"{self.lfo_freq:.2f} Hz")

def _fmt_lfo_shape(self) -> str:
    options = [("sine","SIN"),("triangle","TRI"),("sample_hold","S&H"),("square","SQR")]
    parts = [f"[bold #00ff00 reverse]{t}[/]" if self.lfo_shape==k else f"[#446644]{t}[/]"
             for k,t in options]
    line  = " ".join(parts)
    plain = " ".join(t for _,t in options)
    pad   = max(0, self._W - len(plain)); lp = pad//2; rp = pad-lp
    return f"[#00cc00]│[/]{' '*lp}{line}{' '*rp}[#00cc00]│[/]"

def _fmt_lfo_target(self) -> str:
    options = [("vco","VCO"),("vcf","VCF"),("vca","VCA"),("all","ALL")]
    parts = [f"[bold #00ff00 reverse]{t}[/]" if self.lfo_target==k else f"[#446644]{t}[/]"
             for k,t in options]
    line  = " ".join(parts)
    plain = " ".join(t for _,t in options)
    pad   = max(0, self._W - len(plain)); lp = pad//2; rp = pad-lp
    return f"[#00cc00]│[/]{' '*lp}{line}{' '*rp}[#00cc00]│[/]"
```

**Replace `_adjust_focused_param` stub** (`# Dummy sections — not yet wired`):
```python
elif sec == "lfo":
    if   name == "Rate":   self._do_adjust_lfo_rate(direction)
    elif name == "Depth":  self._do_adjust_lfo_depth(direction)
    elif name == "Shape":  self._do_cycle_lfo_shape(direction)
    elif name == "Target": self._do_cycle_lfo_target(direction)
```

**New `_do_*` helpers**:
```python
def _do_adjust_lfo_rate(self, direction: str):
    factor = 1.15 if direction == "up" else 1.0/1.15
    self.lfo_freq = float(np.clip(self.lfo_freq * factor, 0.1, 20.0))
    self.synth_engine.update_parameters(lfo_freq=self.lfo_freq)
    if self.lfo_rate_display: self.lfo_rate_display.update(self._fmt_lfo_rate())
    self._mark_dirty(); self._autosave_state()

def _do_adjust_lfo_depth(self, direction: str):
    self.lfo_depth = float(np.clip(self.lfo_depth + (0.05 if direction=="up" else -0.05), 0.0, 1.0))
    self.synth_engine.update_parameters(lfo_depth=self.lfo_depth)
    if self.lfo_depth_display:
        self.lfo_depth_display.update(self._fmt_knob(self.lfo_depth, 0.0, 1.0, f"{int(self.lfo_depth*100)}%"))
    self._mark_dirty(); self._autosave_state()

def _do_cycle_lfo_shape(self, direction: str):
    shapes = ["sine","triangle","sample_hold","square"]
    idx = shapes.index(self.lfo_shape) if self.lfo_shape in shapes else 0
    self.lfo_shape = shapes[(idx + (1 if direction=="up" else -1)) % len(shapes)]
    self.synth_engine.update_parameters(lfo_shape=self.lfo_shape)
    if self.lfo_shape_display: self.lfo_shape_display.update(self._fmt_lfo_shape())
    self._mark_dirty(); self._autosave_state()

def _do_cycle_lfo_target(self, direction: str):
    targets = ["vco","vcf","vca","all"]
    idx = targets.index(self.lfo_target) if self.lfo_target in targets else 3
    self.lfo_target = targets[(idx + (1 if direction=="up" else -1)) % len(targets)]
    self.synth_engine.update_parameters(lfo_target=self.lfo_target)
    if self.lfo_target_display: self.lfo_target_display.update(self._fmt_lfo_target())
    self._mark_dirty(); self._autosave_state()
```

**Wire into `_apply_params`, `_push_params_to_engine`, `_current_params`, `_refresh_all_displays`**
following the exact same pattern used for `filter_mode` / `resonance`.

---

## Phase 2 — FX Delay

### What changes
A stereo ring-buffer delay. Applied **post-mix, post-chorus, pre-tanh**.
Rev Size stays in the UI as a greyed-out placeholder (future reverb).

### 2-A  `preset_manager.py`
Add after Phase 1 keys:
```python
"delay_time":     0.25,   # s, 0.05–2.0
"delay_feedback": 0.3,    # 0.0–0.9
"delay_mix":      0.0,    # 0.0–1.0 wet/dry
```

### 2-B  `synth_engine.py` — `__init__`
```python
# ── FX Delay ────────────────────────────────────────────────────────
self.delay_time      = 0.25
self.delay_feedback  = 0.3
self.delay_mix       = 0.0
_dly_buf_len = int(self.sample_rate * 2.0) + 1   # max 2 s
self._delay_buf_l    = np.zeros(_dly_buf_len, dtype=np.float32)
self._delay_buf_r    = np.zeros(_dly_buf_len, dtype=np.float32)
self._delay_write    = 0
self._delay_samples  = int(self.delay_time * self.sample_rate)
```

### 2-C  `synth_engine.py` — `_process_midi_events` special case
Inside the `param_update` elif chain, before the `else: setattr` fallthrough:
```python
elif k == 'delay_time':
    self.delay_time    = float(v)
    self._delay_samples = max(1, min(int(v * self.sample_rate),
                                     len(self._delay_buf_l) - 1))
```

### 2-D  `synth_engine.py` — `_audio_callback` insertion
**After** the chorus block (Phase 3 will sit here first — insert delay after chorus).
Since we build delay before chorus is coded, insert **after the voice loop and before
`_filter_ramp`**. When Phase 3 adds chorus, chorus goes *above* delay.
```python
# ── FX Delay (stereo ring buffer, pre-tanh) ───────────────────────
if self.delay_mix > 0.0:
    buf_len = len(self._delay_buf_l)
    dm = float(self.delay_mix)
    fb = float(self.delay_feedback)
    ds = self._delay_samples
    for i in range(frame_count):
        wp = self._delay_write % buf_len
        rp = (wp - ds) % buf_len
        wet_l = self._delay_buf_l[rp]
        wet_r = self._delay_buf_r[rp]
        self._delay_buf_l[wp] = mixed_l[i] + fb * wet_l
        self._delay_buf_r[wp] = mixed_r[i] + fb * wet_r
        mixed_l[i] = mixed_l[i] * (1.0 - dm) + wet_l * dm
        mixed_r[i] = mixed_r[i] * (1.0 - dm) + wet_r * dm
        self._delay_write = (wp + 1) % buf_len
```

### 2-E  `synth_mode.py`
**Update `_SECTION_PARAMS["fx"]`**:
```python
"fx": ["Delay Time", "Delay Fdbk", "Delay Mix", "Rev Size"],
```

**New instance vars**, compose section, formatters, `_do_*` helpers, dispatch branch.

**New formatter**:
```python
def _fmt_delay_time(self) -> str:
    import math
    norm = (math.log10(max(0.05, self.delay_time)) - math.log10(0.05)) / (math.log10(2.0) - math.log10(0.05))
    ms = int(self.delay_time * 1000)
    label = f"{ms}ms" if ms < 1000 else f"{self.delay_time:.2f}s"
    return self._fmt_knob(norm, 0.0, 1.0, label)

def _fmt_disabled_param(self, label: str = "future") -> str:
    text = f"[ {label} ]"
    pad  = max(0, self._W - len(text)); lp = pad//2; rp = pad-lp
    return f"[#00cc00]│[/]{' '*lp}[dim #334433]{text}[/]{' '*rp}[#00cc00]│[/]"
```

Rev Size row in compose uses `_fmt_disabled_param("future")` and the dispatch branch
has `elif name == "Rev Size": pass`.

---

## Phase 3 — Chorus (BBD Tape-Style)

### What changes
A stereo modulated delay with 1–4 LFO-modulated read taps. Applied **post-mix, before
the delay**. Uses a single ring buffer (shared read, write once per sample).

### 3-A  `preset_manager.py`
```python
"chorus_rate":   0.5,   # Hz, 0.1–10.0
"chorus_depth":  0.0,   # 0.0–1.0 → 0–25ms sweep
"chorus_mix":    0.0,   # 0.0–1.0 wet/dry
"chorus_voices": 2,     # int 1–4
```

### 3-B  `synth_engine.py` — `__init__`
```python
# ── Chorus ──────────────────────────────────────────────────────────
self.chorus_rate   = 0.5
self.chorus_depth  = 0.0
self.chorus_mix    = 0.0
self.chorus_voices = 2
_cho_buf_len = int(self.sample_rate * 0.030) + 2   # 30ms max + guard
self._chorus_buf_l  = np.zeros(_cho_buf_len, dtype=np.float32)
self._chorus_buf_r  = np.zeros(_cho_buf_len, dtype=np.float32)
# 4 chorus LFO phases spread 90° apart
self._chorus_phases = [i * (np.pi / 2.0) for i in range(4)]
self._chorus_write  = 0
```

### 3-C  `synth_engine.py` — `_audio_callback` insertion
Insert **after the voice loop** (after `mixed_r += ...`) and **before the delay block**:
```python
# ── Chorus (BBD-style, post-mix, pre-delay) ──────────────────────
if self.chorus_mix > 0.0:
    n_voices     = int(np.clip(self.chorus_voices, 1, 4))
    buf_len      = len(self._chorus_buf_l)
    _max_dly_smp = self.sample_rate * 0.025   # 25ms max sweep
    cho_l        = np.zeros(frame_count, dtype=np.float32)
    cho_r        = np.zeros(frame_count, dtype=np.float32)
    phase_inc    = 2 * np.pi * self.chorus_rate / self.sample_rate
    for i in range(frame_count):
        wp = self._chorus_write % buf_len
        self._chorus_buf_l[wp] = mixed_l[i]
        self._chorus_buf_r[wp] = mixed_r[i]
        wet_l = wet_r = 0.0
        for v in range(n_voices):
            self._chorus_phases[v] = (self._chorus_phases[v] + phase_inc) % (2 * np.pi)
            base_dly = int(self.sample_rate * 0.0005)   # 0.5ms base
            mod_dly  = int(np.sin(self._chorus_phases[v]) * self.chorus_depth * _max_dly_smp)
            rp = (wp - max(1, base_dly + mod_dly)) % buf_len
            wet_l += self._chorus_buf_l[rp]
            wet_r += self._chorus_buf_r[rp]
        self._chorus_write = (wp + 1) % buf_len
        scale = 1.0 / n_voices
        mx    = float(self.chorus_mix)
        cho_l[i] = mixed_l[i] * (1.0 - mx) + wet_l * scale * mx
        cho_r[i] = mixed_r[i] * (1.0 - mx) + wet_r * scale * mx
    mixed_l = cho_l
    mixed_r = cho_r
```

### 3-D  `synth_mode.py`
Replace dummy chorus section in `compose()`. Add `_fmt_chorus_rate()` (log 0.1–10 Hz)
and `_fmt_chorus_voices()` (selector 1/2/3/4). Add `_do_*` helpers and dispatch branch
for all four params.

---

## Phase 4 — Shared BPM + Arpeggiator

### What changes (4 sub-steps in order)

#### 4-A  `config_manager.py` — shared BPM
Add to `_default_config`:
```python
"metronome_bpm": 120,
```
Add two new public methods:
```python
def get_bpm(self) -> int:
    return int(self.config.get("metronome_bpm", 120))

def set_bpm(self, bpm: int):
    self.config["metronome_bpm"] = int(max(50, min(300, bpm)))
    self.save_config()
```

#### 4-B  `main.py` — pass `config_manager` to MetronomeMode
Change `_create_metronome_mode`:
```python
def _create_metronome_mode(self):
    return MetronomeMode(self.config_manager)
```

#### 4-C  `metronome_mode.py` — read/write shared BPM
Change `__init__` signature:
```python
def __init__(self, config_manager=None):
    super().__init__()
    self.config_manager = config_manager
    self.tempo = config_manager.get_bpm() if config_manager else 120
    # ... rest unchanged
```
In `action_increase_tempo` and `action_decrease_tempo`, add after `self.tempo = ...`:
```python
if self.config_manager:
    self.config_manager.set_bpm(self.tempo)
```

#### 4-D  `preset_manager.py`
```python
"arp_enabled": False,
"arp_mode":    "up",    # "up" | "down" | "up_down" | "random"
"arp_gate":    0.5,     # 0.05–1.0
"arp_range":   1,       # 1–4 octaves
```
**Note: `arp_bpm` is NOT in the preset** — it lives in `config_manager` (shared with metronome).

#### 4-E  `synth_engine.py` — `__init__`
```python
# ── Arpeggiator ─────────────────────────────────────────────────────
self.arp_enabled  = False
self.arp_mode     = "up"
self.arp_bpm      = 120.0
self.arp_gate     = 0.5
self.arp_range    = 1
# Sequencer state (audio-thread only)
self._arp_held_notes:     list         = []
self._arp_sequence:       list         = []
self._arp_index:          int          = 0
self._arp_step_samples:   int          = int(60.0/120.0 * self.sample_rate)
self._arp_sample_counter: int          = 0
self._arp_note_playing:   Optional[int]= None
self._arp_gate_samples:   int          = int(60.0/120.0 * self.sample_rate * 0.5)
self._arp_direction:      int          = 1   # for up_down: +1 or -1
```

#### 4-F  `synth_engine.py` — new helper methods
```python
def _arp_rebuild_sequence(self):
    """Build the expanded note list from held notes × octave range."""
    if not self._arp_held_notes:
        self._arp_sequence = []; return
    base = sorted(set(self._arp_held_notes))
    seq  = []
    for shift in range(int(self.arp_range)):
        for note in base:
            t = note + shift * 12
            if t <= 127: seq.append(t)
    self._arp_sequence = seq
    if seq: self._arp_index = self._arp_index % len(seq)

def _arp_next_index(self) -> int:
    """Advance and return next sequence index based on arp_mode."""
    n = len(self._arp_sequence)
    if self.arp_mode == "up":
        idx = self._arp_index % n
        self._arp_index = (self._arp_index + 1) % n
    elif self.arp_mode == "down":
        idx = (n - 1 - self._arp_index % n)
        self._arp_index = (self._arp_index + 1) % n
    elif self.arp_mode == "up_down":
        idx = self._arp_index % n
        nxt = self._arp_index + self._arp_direction
        if nxt >= n:   self._arp_direction = -1; nxt = max(0, n-2)
        elif nxt < 0:  self._arp_direction =  1; nxt = min(1, n-1)
        self._arp_index = nxt
    else:  # random
        idx = _rnd.randrange(n)
        self._arp_index = idx
    return idx

def _arp_recalc_timing(self):
    """Recompute step and gate sample counts."""
    self._arp_step_samples = max(1, int(60.0 / max(1.0, self.arp_bpm) * self.sample_rate))
    self._arp_gate_samples = max(1, int(self._arp_step_samples * float(self.arp_gate)))
```

#### 4-G  `synth_engine.py` — `_process_midi_events`
**Special-case arp params** (in `param_update` elif chain, before `else: setattr`):
```python
elif k == 'arp_bpm':
    self.arp_bpm = float(v); self._arp_recalc_timing()
elif k == 'arp_gate':
    self.arp_gate = float(v); self._arp_recalc_timing()
elif k == 'arp_range':
    self.arp_range = int(v); self._arp_rebuild_sequence()
elif k == 'arp_enabled':
    self.arp_enabled = bool(v)
    if not self.arp_enabled:
        if self._arp_note_playing is not None:
            self._release_note(self._arp_note_playing)
            self._arp_note_playing = None
    self._arp_sample_counter = 0
elif k == 'arp_mode':
    self.arp_mode = v; self._arp_index = 0; self._arp_direction = 1
```

**Intercept note events** in the second pass (replace the existing `if e['type'] == 'note_on': self._trigger_note(...)` block):
```python
if e['type'] == 'note_on':
    if self.arp_enabled:
        n = e['note']
        if n not in self._arp_held_notes: self._arp_held_notes.append(n)
        self._arp_rebuild_sequence()
        self.held_notes.add(n)
    else:
        self._trigger_note(e['note'], e['velocity'])
    note_events_processed += 1
elif e['type'] == 'note_off':
    n = e['note']
    if self.arp_enabled:
        if n in self._arp_held_notes: self._arp_held_notes.remove(n)
        self._arp_rebuild_sequence()
        if not self._arp_held_notes and self._arp_note_playing is not None:
            self._release_note(self._arp_note_playing)
            self._arp_note_playing = None
        self.held_notes.discard(n)
    else:
        self._release_note(e['note'], e.get('velocity', 0.5))
    note_events_processed += 1
```

Also extend the `all_notes_off` branch to clear arp state:
```python
elif e['type'] == 'all_notes_off':
    for v in self.voices: v.reset()
    self._arp_held_notes.clear(); self._arp_sequence.clear()
    self._arp_note_playing = None; self._arp_sample_counter = 0
```

#### 4-H  `synth_engine.py` — `_audio_callback` arpeggiator clock
Insert **immediately after `self._process_midi_events()`** and before `self._update_voice_frequencies()`:
```python
# ── Arpeggiator clock (audio-callback driven, sample-accurate grid) ──
if self.arp_enabled and self._arp_sequence:
    self._arp_sample_counter += frame_count
    # Gate-off: release note when gate period expires
    if (self._arp_note_playing is not None
            and self._arp_sample_counter > self._arp_gate_samples):
        self._release_note(self._arp_note_playing)
        self._arp_note_playing = None
    # Step: advance to next note at step boundary
    if self._arp_sample_counter >= self._arp_step_samples:
        self._arp_sample_counter -= self._arp_step_samples   # carry remainder
        idx  = self._arp_next_index()
        note = self._arp_sequence[idx]
        self._trigger_note(note, 1.0)
        self._arp_note_playing = note
```

#### 4-I  `synth_mode.py` — Arpeggio UI
**Update `_SECTION_PARAMS["arpeggio"]`**:
```python
"arpeggio": ["Mode", "Rate", "Gate", "Range", "ON/OFF"],
```

**New instance vars**:
```python
self.arp_enabled = params.get("arp_enabled", False)
self.arp_mode    = params.get("arp_mode",    "up")
self.arp_bpm     = float(self.config_manager.get_bpm())  # from shared BPM, not preset
self.arp_gate    = params.get("arp_gate",    0.5)
self.arp_range   = params.get("arp_range",   1)
# widget refs
self.arp_mode_display  = None
self.arp_rate_display  = None
self.arp_gate_display  = None
self.arp_range_display = None
self.arp_onoff_display = None
```

**Replace dummy arpeggio section** in `compose()` with live widgets.

**New formatters**:
```python
def _fmt_arp_mode(self) -> str:
    options = [("up","UP"),("down","DN"),("up_down","U+D"),("random","RND")]
    # same selector pattern as _fmt_filter_mode / _fmt_lfo_shape

def _fmt_arp_range(self) -> str:
    options = ["1","2","3","4"]
    # same _fmt_dummy_selector pattern

def _fmt_arp_onoff(self) -> str:
    # Two-option toggle: ON (green reverse) / OFF (dim)
```

**Dispatch branch**:
```python
elif sec == "arpeggio":
    if   name == "Mode":   self._do_cycle_arp_mode(direction)
    elif name == "Rate":   self._do_adjust_arp_bpm(direction)
    elif name == "Gate":   self._do_adjust_arp_gate(direction)
    elif name == "Range":  self._do_adjust_arp_range(direction)
    elif name == "ON/OFF": self._do_toggle_arp_enabled(direction)
```

**`_do_adjust_arp_bpm`** writes back to `config_manager.set_bpm()` so metronome picks it up next visit.

**`_apply_params`** reads `arp_bpm` from `config_manager.get_bpm()` (not from preset dict) — this ensures the metronome's last BPM is always respected.

---

## Backward Compatibility

All new keys in `DEFAULT_PARAMS` become automatic fallbacks for old presets via
`extract_params`'s `dict(DEFAULT_PARAMS)` base + update pattern. No migration needed.

All new params default to their "bypassed" state:
- `lfo_depth = 0.0` → no LFO effect
- `delay_mix = 0.0` → delay bypassed
- `chorus_mix = 0.0` → chorus bypassed
- `arp_enabled = False` → normal polyphonic play

---

## Versioning Plan

| Phase | Version | Commit message |
|-------|---------|----------------|
| 1     | v1.5.0  | `feat: LFO shape selector and per-target depth routing` |
| 2     | v1.5.1  | `feat: FX delay with feedback and wet/dry mix` |
| 3     | v1.5.2  | `feat: BBD-style chorus with 1-4 modulated voices` |
| 4     | v1.5.3  | `feat: arpeggiator with shared BPM and metronome sync` |

---

## Key Design Decisions

1. **`lfo_depth` replaces separate `lfo_vco/vcf/vca_mod` in the UI** — the three backing
   attributes stay in the engine for direct access but are now computed from `depth + target`
   per buffer. Old presets that have non-zero `lfo_vco_mod` etc. will not be overridden
   on load (those attrs are still set via `setattr`), but the new UI controls only expose
   depth+target. This is a clean separation.

2. **Chorus before Delay** in the signal chain (industry standard: chorus widens then delay
   echoes the widened signal).

3. **`arp_bpm` not saved in presets** — it belongs to the performance context (tempo), not
   the sound design (timbre). Saved/loaded via `config_manager` so it persists across
   sessions and syncs with the metronome.

4. **Audio-callback arpeggiator clock** (not a Python timer thread) — the counter increments
   by `frame_count` each callback and carries the modulo remainder into the next step.
   This gives ±1-buffer (≈5.3ms) timing accuracy with zero additional threads.

5. **`Rev Size` placeholder** — kept as a greyed-out `_fmt_disabled_param("future")` row
   in the FX section. The `_SECTION_PARAMS` entry remains `"Rev Size"` but the dispatch
   branch does `pass`. When reverb is implemented it drops in cleanly.
