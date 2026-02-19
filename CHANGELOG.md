# Changelog

All notable changes to the Acordes MIDI Piano TUI Application will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.3] - 2026-02-19

### Fixed
- **Low-frequency onset thump** (`music/synth_engine.py`): Sine waveform at octave=-2 with short attack produced an audible thump on note onset. Root cause: the DC blocker (coeff=0.999, pole at 2.4 Hz) has a ~66 ms settling time at 55 Hz, but the onset ramp was a fixed 3 ms — covering less than 1/6 of a 55 Hz cycle.
  - **Frequency-adaptive `ONSET_RAMP`**: Duration now computed as `max(3ms, min(30ms, 1.5 × period_ms))` per voice, stored in `voice.onset_ms` set at trigger time. At 55 Hz: 27 ms; at 440 Hz: 3 ms (unchanged — no regression at mid/high frequencies).
  - **Frequency-adaptive `ANTI_I`**: Envelope soft-start window in `_apply_envelope` now reads `voice.onset_ms / 1000.0` instead of the hardcoded 5 ms constant, matching the onset ramp duration so the exponential attenuation covers the DC blocker's full settling window.
  - **Adaptive DC blocker coefficient** (`_apply_dc_blocker`): Coefficient is now computed per-voice based on `voice.frequency` — `0.9990` above 100 Hz (pole 2.4 Hz, standard behaviour), linearly interpolated to `0.9997` below 50 Hz (pole ≈ 0.7 Hz). This reduces phase distortion at very low fundamentals; combined with the longer onset ramp, the onset transient is fully hidden.
- **Randomize click on held notes** (`music/synth_engine.py`, `modes/synth_mode.py`): Pressing `-` (randomize) while a note was held caused an audible click because `waveform`, `octave`, and envelope parameters (`attack`, `decay`, `sustain`, `release`) were applied via `setattr` instantly on the next audio buffer — creating mid-note frequency, waveshape, and amplitude discontinuities.
  - **Output mute gate** (`_mute_ramp_remaining` / `_mute_ramp_fadein` / `_MUTE_RAMP_LEN=384`): A new `'mute_gate'` event type arms a ~8 ms (384-sample) fade-out ramp on the mixed output. When the fade-out completes, a matching fade-in is automatically queued. Both the `mute_gate` and `param_update` events are drained in the same `_process_midi_events()` call, so the new params are applied under silence and the fade-in plays with the new waveform/octave already active.
  - `action_randomize` now enqueues `{'type': 'mute_gate'}` before `_push_params_to_engine()` so the gate is always armed before any parameter changes land on the audio thread.

## [1.4.2] - 2026-02-19

### Changed
- **Synth Mode focus navigation overhaul** (`modes/synth_mode.py`):
  - Up/Down arrows now cross section row boundaries — pressing Up at the first param of a section jumps to the last param of the same column in the adjacent row. All 8 sections (including LFO, Chorus, FX, Arpeggio) are reachable without mouse.
  - Added **Alt+Left / Alt+Right** bindings to decrease/increase the focused parameter value as an alternative to Q/W.
  - **Q** now decreases and **W** increases the focused parameter (was Q increase / A decrease). In legacy (unfocused) mode, Q/W adjusts octave down/up.
  - Added **,** (comma) and **.** (full\_stop) bindings for preset cycling — work in both focus and legacy modes.
  - All letter-key legacy shortcuts (E/D, R/F, T/G, Y/H, U/J, O/L, etc.) are silently suppressed while in focus mode to prevent accidental edits during navigation.

### Fixed
- **Synth Mode `IndexError: list index out of range`** (`modes/synth_mode.py`): When navigating left/right between sections, the param index was not clamped to the new section's param count. `_set_focus` now clamps on every section change.
- **Synth Mode Q/W (and Alt+←/→) had no effect in focus mode** (`modes/synth_mode.py`): The focus dispatch called the guarded `action_*` methods which immediately returned when focused. Extracted `_do_*` private helpers (no guard) for the actual engine mutations; `action_*` methods are now thin wrappers that guard then delegate; `_adjust_focused_param` calls `_do_*` directly.
- **Escape did not open quit dialog when unfocused** (`modes/synth_mode.py`): `action_nav_escape` was consuming the key event even when there was nothing to unfocus. Now calls `self.screen.action_quit_app()` when not focused.
- **`.` (full\_stop) preset-next binding had no effect** (`modes/synth_mode.py`): Textual 7.5 maps the `.` character to the key name `full_stop`, not `period`. Binding corrected.

## [1.4.1] - 2026-02-18

### Fixed
- **OS audio thread priority** (`music/synth_engine.py`): PortAudio callback thread now receives elevated OS scheduling priority at startup to prevent the Textual UI thread from starving it during widget rebuilds (mode switches).
  - **Windows**: `SetPriorityClass(ABOVE_NORMAL_PRIORITY_CLASS)` via `ctypes/kernel32` — no admin rights required.
  - **Linux**: `SCHED_FIFO` real-time scheduling via `pthread_setschedparam` + `PR_SET_TIMERSLACK` (100 µs) for tighter sleep granularity. Falls back to `os.nice(-10)` without `CAP_SYS_NICE`.
  - **macOS**: Mach `thread_policy_set(THREAD_TIME_CONSTRAINT_POLICY)` — the same API used by Core Audio. Falls back to `os.nice(-10)` on failure.
  - All paths are silent on failure — audio still works, just with less OS scheduling protection.
- **Thread-safe parameter routing** (`music/synth_engine.py`): `update_parameters()` and `all_notes_off()` now enqueue events rather than writing directly to shared attributes from the UI thread. Applied on the audio thread at the next buffer boundary, eliminating 25+ cross-thread data races that caused clicks when moving ADSR/filter knobs or switching modes while notes were playing.
- **Per-sample master gain ramp** (`music/synth_engine.py`): Voice count is now pre-calculated before the mixing loop so `gain_ramp` (via `np.linspace`) targets the correct value for the current buffer — previously lagged one buffer behind, producing a residual step discontinuity on voice-count changes.
- **Smooth silence gain decay** (`music/synth_engine.py`): `master_gain_current` now decays smoothly toward 1.0 during silence (coefficient 0.90/buffer) instead of hard-resetting, preventing a level spike on the first buffer after a silent gap. Smoothing coefficient tightened `0.98 → 0.80` so gain tracks voice-count changes within ~2 buffers (~10 ms).
- **Per-voice onset ramp** (`music/synth_engine.py`): 3 ms linear fade-in applied to each voice's post-envelope signal before the DC blocker on every new trigger. Suppresses the DC blocker's differentiator startup transient (first-sample high-frequency click) that was most audible on square and sawtooth waveforms at non-zero oscillator phases.
- **ANTI_I extended and repositioned** (`music/synth_engine.py`): Onset soft-start window extended from 2 ms to 5 ms to cover the DC blocker settling time. Moved to after the CROSS voice-steal crossfade so stolen voices still start from their pre-steal level — ANTI_I only attenuates, so both mechanisms compose cleanly.
- **Voice steal filter zero** (`music/synth_engine.py`): Filter and DC blocker states are explicitly zeroed before `trigger()` on a stolen voice, preventing stale frequency-domain state from the old note from bleeding into the new note's first few output samples.
- **Piano mode `on_mount`/`on_unmount`** (`modes/piano_mode.py`): Restored correct lifecycle structure — a linter had relocated `set_interval` and display initialisation into `on_unmount`, causing Piano Mode to show no display and produce no sound on first visit without a prior Synth Mode visit.
- **Stereo centre for single notes** (`music/synth_engine.py`): Pan table reordered so voice 0 (always the first triggered for any single note) is at `pan=0.5` — previously `0.35`, causing a ~63% L/R power imbalance on solo notes. Subsequent voices spread symmetrically outward in pairs.
- **tanh drive reduced** (`music/synth_engine.py`): `comp` multiplier lowered (`1.4 → 0.9` for sine) and post-tanh makeup gain added, keeping sustain-level signals in tanh's linear region. Eliminates the attack-peak/sustain-sag shape caused by differential saturation at different envelope stages.

## [1.3.0] - 2026-02-17

### Added
- **Yamaha CS-80 Precision Emulation**:
  - **Dual Rank Architecture**: Each note triggers two independent synthesis paths (Rank I and Rank II) with individual waveform and filter settings.
  - **Series Filtering**: Implemented hardware-accurate 12dB/oct series filtering (High-Pass Filter into Low-Pass Filter) per rank.
  - **Sine Reinforcement**: Added a pure sine wave reinforcement path post-filter to maintain low-end body during aggressive filtering.
  - **Global Sub-Oscillator (LFO)**: Central modulation bus controlling VCO (Pitch), VCF (Filter), and VCA (Volume) across all voices.
- **Advanced MIDI Support**:
  - **Note-Off (Release) Velocity**: Full support for MIDI release velocity, allowing the speed of key release to modulate the sound's decay/release characteristic.
- **Master Section**:
  - **Master Volume Control**: Post-saturation global output control using **[** and **]** shortcuts.
  - **Smoothed Gain Protection**: Fast-acting gain ducking and smoothing to prevent clipping during polyphonic changes.

### Changed
- **8-Voice Polyphony**: Adjusted voice limit to 8 to match original CS-80 hardware specifications.
- **MIXER UI Redesign**: Updated the synth interface with a dedicated MIXER section for Preset and Master levels.
- **Waveform Selection**: Expanded to 5 waveforms, including a new **Pure Sine (PSIN)** alongside the original Warm Sine (SIN).
- **Narrower Stereo Field**: Refined voice panning from wide 20/80 to a more centered 40/60 for a solid, hardware-like stereo image.

### Optimized
- **Full DSP Vectorization**: Eliminated Python loops in the audio callback. Oscillators, ADSR envelopes, filters, and DC blockers are now fully vectorized using NumPy and SciPy.
- **Zero-Latency DC Blocking**: Refactored the DC blocker with high damping (0.999) and state initialization to eliminate "DC Crush" and tonality drift.
- **Click-Free Performance**: Restored free-running oscillators and implemented buffer-boundary gain smoothing for perfectly clean transients.

### Fixed
- **Tonality Drift**: Resolved an issue where held notes changed timbre over time due to slow DC blocker settling.
- **Attack Blast**: Fixed a volume spike occurring at note onset by implementing instant headroom protected gain adjustment.
- **Settings Leak**: Fixed a bug where LFO and Rank II parameters would persist when switching between presets.

## [1.2.0] - 2026-02-17

### Added
- **Synth Preset System** (`music/preset_manager.py` — new module):
  - 10 factory presets covering a wide sonic range: `default`, `warm_pad`, `bright_saw_lead`, `deep_bass`, `soft_strings`, `church_organ`, `glass_bells`, `hollow_reed`, `plucky_square`, `vintage_synth`.
  - Presets stored as individual JSON files in `presets/` — easy to share, back up, or hand-edit.
  - Two-tier ordering: factory presets sorted alphabetically, user presets appended in creation order (newest always at end).
  - Save a new preset at any time with **Ctrl+N** — gets a randomly generated bilingual (English + European Portuguese) musical name (e.g. *amber reed*, *escuro sino*, *vazio echo*).
  - Update / overwrite the currently loaded preset with **Ctrl+S**.
  - Cycle through all presets with **,** (previous) and **.** (next).
  - Preset bar above the synth boxes shows `[index/total] Preset Name` with a `*` dirty marker after any parameter change.
  - Over ~1 500 unique bilingual name combinations from curated adjective + noun word banks.
- **Synth State Persistence**:
  - All synth parameters autosaved to `config.json` (`synth_state` key) on every change.
  - Last active preset filename stored in `config.json` (`last_synth_preset` key) and restored on next launch.
  - Restore priority on startup: last preset file → `synth_state` fallback → hardcoded defaults.
- **Synth Randomizer** (`-` key):
  - Generates a complete random patch using musically weighted distributions:
    - Waveform: equal probability across all four types.
    - Octave: weighted towards 8' (centre) for playability.
    - Cutoff: log-uniform 200 Hz–18 kHz for natural timbral variety.
    - Resonance: weighted 50/35/15% across subtle / moderate / resonant ranges.
    - Attack & Decay: log-uniform 1 ms–2 s; Release: log-uniform 10 ms–3 s.
    - Sustain: weighted 25/35/40% across percussive / expressive / pad ranges.
    - Amplitude: uniform 50–95%; Intensity: uniform 40–100%.
  - Immediately marks state dirty and autosaves parameters.

### Changed
- **`config_manager.py`**: Added `get_last_preset()`, `set_last_preset()`, `get_synth_state()`, `set_synth_state()` methods; `_default_config()` now includes `last_synth_preset` and `synth_state` keys.
- **`modes/synth_mode.py`**: Full integration of `PresetManager` and `ConfigManager`; constructor now accepts the shared `SynthEngine` and `ConfigManager` instead of creating its own engine.
- **`main.py`**: `_create_synth_mode()` now passes the shared `synth_engine` and `config_manager` to `SynthMode`, resolving the double-engine bug.

### Fixed
- **Piano Mode audio glitches when MIDI keys are held**:
  - Root cause: `_poll_midi` unconditionally called `_update_display` every 10 ms (100×/second), causing heavy Textual render work (piano widget, chord display, staff widget) to compete with the PyAudio audio callback thread.
  - Fix: added change-detection guard (`_last_displayed_notes`) — display updates only when the active note set actually changes.
  - Removed `header.update_subtitle()` from the polling hot loop (MIDI connection status never changes during play).
- **Double SynthEngine bug**: `SynthMode` was previously instantiating its own private `SynthEngine`, independent of the shared instance used by `PianoMode` and `CompendiumMode`. Now all modes share a single engine via `app_context`.
- **New user presets appearing alphabetically instead of at the end**: `PresetManager._reload()` now uses a two-tier sort so user presets always append in creation-time order after the factory set.

## [1.1.1] - 2026-02-17

### Added
- **Unified Header System**: Introduced `HeaderWidget` in `components/header_widget.py` for consistent visual branding across all modes.
  - Supports both large ASCII art titles and modern boxed titles.
  - Centered subtitle/status labels for better readability.
  - Dynamic status updates (e.g., MIDI connection status, currently playing note/velocity).
- **Chord Playback in Compendium**:
  - Automatically plays the selected chord when navigating through the Chord Compendium tree.
  - Manual playback triggered with **SPACE** key.
  - Implemented musical "strum" effect (staggered note onset) for a more natural sound.
  - Smart note-to-MIDI conversion logic handling sharps, flats, and octave offsets.
- **Audio "Warm-up" System**: 
  - Added `warm_up()` method to `SynthEngine` to prime PyAudio buffers during application startup.
  - Eliminates initial "hiccups" or lag when the first note is played in any mode.

### Changed
- **Piano Logic Refactor**: 
  - Unified all piano rendering into a single, reusable `PianoWidget`.
  - Removed redundant ASCII rendering code from `PianoMode`.
  - `PianoWidget` now features the enhanced "tall key" design with rich coloring.
- **Improved Compendium Navigation**:
  - Rebound **SPACE** to "Play Chord" (was Expand All).
  - Rebound **E** to "Expand All".
  - Audio now triggers on highlight (`on_tree_node_highlighted`) for immediate feedback.
- **Synth Engine Integration**:
  - `PianoMode` now features full real-time audio playback using the `SynthEngine` for all MIDI input.
  - Improved `play_chord` responsiveness using `threading.Timer` for precise release timing.

### Fixed
- Fixed several Python syntax and indentation errors introduced during refactoring.
- Centered all header subtitles which were previously left-aligned.
- Resolved audio latency issues during initial mode activation.

## [1.1.0] - 2026-02-16

### Added
- **Metronome Mode**: A new, fully-featured, and musically aware metronome.
  - **Visual Beat Bar**: A large, centered ASCII art bar displays the current beat in the measure. The number of blocks in the bar automatically matches the selected time signature.
  - **Musically Coherent Time Signatures**: Users can cycle through a curated list of common simple (2/4, 3/4, 4/4) and compound (6/8, 9/8, 12/8) time signatures.
  - **Correct Accentuation**: The metronome automatically plays a stronger accent on the musically correct beats for each signature (e.g., on beats 1 and 4 in 6/8 time), providing a more natural feel.
  - **Italian Tempo Markings**: A label displays the traditional Italian name for the current tempo range (e.g., *Andante*, *Allegro*), which updates live as the BPM is changed.
  - **Full Keyboard Control**: Start/Stop, tempo adjustment (50-300 BPM), and time signature cycling are all controlled via the keyboard.

### Changed
- **Application Exit Behavior**:
  - The terminal screen is now automatically cleared upon quitting the application for a cleaner exit.
  - The "Hello from the pygame community" message is now suppressed.

## [1.0.3] - 2026-02-15

### Fixed
- **Synth Mode Layout**: Fixed vertical positioning issue where synth control boxes appeared in the middle of the screen
  - Root cause: Nested container wrappers (#main-content, #title-section) were causing Textual's grid layout to vertically center content
  - Solution: Simplified layout by removing intermediate containers and yielding widgets directly to SynthMode
  - Title and status now properly centered horizontally using Textual's Center container
  - Synth control boxes now appear immediately below the title section with one line spacing
  - Removed unused CSS rules for #main-content and #title-section containers
  - Improved overall layout efficiency and rendering performance

### Changed
- Simplified Synth Mode widget hierarchy for better layout control
- Updated parent container alignment in main.py (#content-area: `align: left top`)
- Cleaner CSS with removal of debug properties and unused containers

## [1.0.2] - 2026-02-15

### Changed
- **Synth Mode UI Redesign**: Complete visual overhaul with professional box layout
  - **Complete ASCII boxes** encompass all sections using mixed box-drawing character set
  - **Box dimensions**: 28 characters wide (increased from 24 for better content fit)
  - **Wider sliders**: Increased from 10 to 24 characters (140% wider, ~4% visual precision)
  - **Side borders**: All parameters enclosed with `│` light vertical borders
  - **Section boxes**: Each section (OSCILLATOR, FILTER, ENVELOPE, AMP) has complete top/bottom borders
  - **Mixed border style**: Double-line corners (╔╗╚╝) + Light horizontal/vertical lines (─│)
  - **Better screen utilization**: Improved layout maximizes terminal space usage
  - **Professional aesthetic**: Hardware synthesizer-inspired visual design with clean, light borders
  - **Consistent formatting**: All controls follow same box pattern throughout
  - **Dynamic value centering**: Values automatically centered in 24-char sliders
  - Box characters: Corners `╔╗╚╝` (double), Horizontal `─` (light), Vertical `│` (light)
  - Parameter format: Each control shows label, slider, and value all within borders
  - Example: `│ Wave [W] │` → `│ SIN SQR SAW TRI │`
  - Slider precision: 24-char sliders show ~4% increments (vs 5% at 20 chars, 10% at 10 chars)
  - Zero performance impact (formatting only at UI update time)

## [1.0.1] - 2026-02-14

### Added
- **Synth Mode**: New 4-voice polyphonic synthesizer mode with real-time MIDI playback
  - Four waveform types: Sine, Square, Sawtooth, and Triangle
  - Oscillator section with visual waveform selection
  - **Octave transpose control** with organ feet notation (32', 16', 8', 4', 2')
    - Range: -2 to +2 octaves (5 selectable positions)
    - Visual position indicator showing current octave
    - Hardware synth-style pitch shifting
  - Low-pass filter with cutoff frequency (20Hz-20kHz) and resonance controls
  - Full ADSR envelope generator (Attack, Decay, Sustain, Release, Intensity)
  - AMP section with master amplitude control
  - **MIDI pitch bend support** (±2 semitones range, standard MIDI)
  - **MIDI modulation wheel support** (CC1 controller)
  - UI organized with ASCII box sections showing clear signal flow
  - Real-time audio synthesis using PyAudio and NumPy
  - Visual parameter sliders with green color theme
  - "SYNTH" ASCII art title in block style

- **Synth Engine** (`music/synth_engine.py`):
  - 4-voice polyphonic architecture (play up to 4 notes simultaneously)
  - Independent voice management with per-voice oscillators, envelopes, and filters
  - **MIDI velocity sensitivity** with natural response curve (square root scaling)
  - **MIDI event queue synchronization** for click-free note triggers
    - Decouples MIDI input thread from audio callback thread
    - All note events processed at audio buffer boundaries
    - Eliminates clicks from mid-buffer note triggers
    - Thread-safe queue-based communication
  - Smart voice stealing algorithm with 3-level priority system
  - Held-note tracking to prevent latching issues
  - Waveform generation for sine, square, sawtooth, and triangle waves
  - MIDI note to frequency conversion (A440 standard)
  - Real-time audio callback system with voice mixing
  - Per-voice low-pass filtering for independent voice processing
  - ADSR envelope (Attack-Decay-Sustain-Release) with smooth 50ms release phase
  - Phase continuity for click-free note transitions
  - Volume control with soft clipping (tanh) for smooth saturation
  - MIDI panic function (all notes off) accessible via SPACE key

- **Interactive Keyboard Controls** (Synth Mode):
  - **W**: Toggle waveform (Sine → Square → Sawtooth → Triangle)
  - **S/X**: Increase/Decrease octave transpose (-2 to +2 octaves)
  - **↑/↓**: Increase/Decrease AMP level (master amplitude)
  - **←/→**: Increase/Decrease filter cutoff frequency
  - **Q/A**: Increase/Decrease resonance
  - **E/D**: Increase/Decrease attack time
  - **R/F**: Increase/Decrease decay time
  - **T/G**: Increase/Decrease sustain level
  - **Y/H**: Increase/Decrease release time
  - **U/J**: Increase/Decrease intensity
  - **SPACE**: Panic (immediately silence all voices)
  - **MIDI Controllers**:
    - **Pitch Bend Wheel**: Real-time pitch modulation (±2 semitones)
    - **Modulation Wheel (CC1)**: Modulation control (ready for LFO routing)

- **Mode Switching Enhancement**:
  - Keyboard shortcut **3** to access Synth Mode
  - Updated mode navigation (Piano: 1, Compendium: 2, Synth: 3)
  - Config mode return logic updated to support all three modes

### Changed
- Updated main application to include Synth Mode in mode switching
- Enhanced README with Synth Mode documentation and keyboard controls
- Updated requirements to include PyAudio, NumPy, and SciPy
- Improved mode navigation with numeric key bindings (1, 2, 3)
- **Redesigned synth parameters for analog/musical feel**:
  - Filter cutoff: Logarithmic scaling (20Hz-20kHz) for natural frequency perception
  - Resonance: Limited to 0-90% to prevent self-oscillation
  - Attack/Decay: Exponential scaling (1ms-5s) for fine control at short times
  - All parameters now use musically-appropriate ranges instead of arbitrary 0.0-1.0
- **Major performance optimizations**:
  - Vectorized ADSR envelope generation using NumPy (eliminates 512-iteration Python loop per voice)
  - Optimized low-pass filter using scipy.signal.lfilter (10x faster than Python loop)
  - Lazy pitch bend updates (only when pitch bend value changes, not every callback)
  - Single-pass voice stealing algorithm (eliminates multiple list comprehensions)
  - Overall ~60% reduction in audio callback CPU usage
- **Audio quality improvements**:
  - **Pitch bend smoothing**: Interpolated pitch wheel values eliminate "jumpy" behavior
  - **Enhanced anti-click protection**: Increased fade-in to 2ms for cleaner note attacks
  - **DC blocker filter**: High-pass filter removes DC offset and low-frequency clicks
  - **Improved phase handling**: Always reset phase on note trigger for consistent starts
  - **Automatic waveform amplitude balancing**: AMP section auto-compensates for waveform differences
    - Automatic gain compensation applied in AMP stage (can be disabled)
    - Sine wave: +2.9dB (1.4x) compensation for better presence
    - Square wave: -1.9dB (0.8x) compensation (square has higher RMS power)
    - Sawtooth/Triangle: +4.6dB (1.7x) compensation to match sine
    - All waveforms now have equal perceived loudness at same AMP setting
  - **Enhanced resonance**: Improved filter resonance with feedback and peak boost
    - Resonance now maps to Q factor (0.5 to 11.0) for more dramatic effect
    - Gain compensation (1.0x to 3.0x) makes resonance peaks more audible
  - Smoother voice stealing with better filter state preservation

### Technical Details
- Audio sample rate: 48000 Hz (professional audio standard, low latency)
- Audio buffer size: 1024 samples (CHUNK size optimized for click-free audio, ~21.3ms latency)
- Audio format: 16-bit PCM (paInt16) - efficient signed integer audio
- Oscillator tuning: **A440 Hz standard** (A4 = MIDI note 69 = 440 Hz)
- Oscillator octave range: -2 to +2 octaves (32' to 2' organ feet notation)
- Polyphony: 4 voices with independent oscillators, envelopes, and filters
- Voice allocation: Smart 3-priority stealing (unheld releasing → any releasing → oldest)
- Voice normalization: Dynamic scaling (√N) to prevent clipping
- Filter: Per-voice one-pole low-pass with resonance feedback and preserved state
- Envelope: Full ADSR (Attack, Decay, Sustain, Release) with configurable parameters
  - Attack/Decay/Release: Exponential scaling (1ms-5s)
  - Sustain: Linear level (0-100%)
  - Intensity: Envelope peak level (0-100%)
- AMP: Master amplitude control (0-100%) applied after voice mixing
  - Automatic waveform gain compensation in AMP stage
  - Compensation factors: Sine 1.4x, Square 0.8x, Sawtooth/Triangle 1.7x
- MIDI Controllers:
  - Pitch bend: ±2 semitones (standard MIDI range, 14-bit resolution)
  - Modulation wheel (CC1): 0-100% (7-bit MIDI CC resolution)
  - Per-voice pitch bend applied in real-time to all active voices
- **MIDI Event Synchronization**:
  - Queue-based architecture decouples MIDI input from audio processing
  - Events processed at buffer boundaries for click-free note triggers
  - Thread-safe queue.Queue() for inter-thread communication
  - Maximum latency: One buffer period (~21.3ms)
  - Zero blocking in audio callback for optimal real-time performance
- Phase continuity maintained across audio buffers for click-free playback
- Anti-click protection: 2ms fade-in at note start to prevent DC offset clicks
- DC blocker: High-pass filter (cutoff ~8Hz) removes DC offset and subsonic clicks
- Pitch bend smoothing: Exponential smoothing factor of 0.85 for natural wheel feel
- Soft clipping using tanh for smooth saturation
- Audio conversion: 32-bit float [-1.0, 1.0] → 16-bit PCM [-32767, 32767]
- Error handling in audio callback to prevent crashes
- Explicit device selection for better Windows compatibility
- Graceful degradation if PyAudio is not installed
- Signal flow visualization: Oscillator → Filter → Envelope → AMP → Output

### Bug Fixes
- Fixed note latching issue caused by monophonic note_off gating in polyphonic mode
- Fixed filter state contamination by implementing per-voice filtering
- Fixed voice stealing conflicts with held-note tracking system
- Eliminated audio clicks/pops through proper release phase implementation
- Fixed filter discontinuities by preserving per-voice filter state across buffers
- **Fixed single-note and simultaneous-note clicks** by implementing MIDI event queue synchronization
  - All note triggers now occur at audio buffer boundaries (not mid-buffer)
  - Separated MIDI input thread from audio processing thread
  - Thread-safe event queue prevents timing-related clicks

### Dependencies Added
- `numpy>=1.24.0` - Numerical computing for audio synthesis
- `pyaudio>=0.2.13` - Real-time audio I/O (optional)
- `scipy>=1.10.0` - Scientific computing library for optimized DSP filters

## [1.0.0] - 2026-02-14

### Added
- **Musical Staff Display**: Traditional music notation with side-by-side Bass and Treble clefs
  - Bass Clef (F) displays notes below B3 (MIDI note 59)
  - Treble Clef (G) displays notes B3 and above
  - Notes appear as yellow dots (●) on staff lines in real-time
  - Sharp notes clearly marked with ♯ symbol
  - Reference note labels (E4, G4, B4, D5, F5 for treble; G2, B2, D3, F3, A3 for bass)
  - Side-by-side layout with proper spacing and alignment
  - Staff width: 30 characters per clef for optimal display

- **Chord Display Component**: Dedicated widget for showing detected chords
  - Displays above the piano keyboard for better visibility
  - Centered alignment with consistent height to prevent layout shifts
  - Color-coded display:
    - Single notes: Cyan (#00d7ff)
    - Detected chords: Green (#00ff87)
    - Multiple notes (no chord): Gold (#ffd700)
  - Placeholder dash (─) when no notes playing to maintain layout stability

- **Layout Improvements**:
  - MIDI status message ("🎵 MIDI device connected - Play some notes!") moved below title
  - Centered status message for better visual hierarchy
  - Optimized section heights for better space distribution
  - Title section: ACORDES ASCII art + status
  - Chord display: Positioned above piano
  - Piano section: 3-octave visual keyboard
  - Staff section: Side-by-side Bass and Treble clefs

### Changed
- Enhanced piano mode layout with 4 distinct sections
- Improved visual spacing between UI elements
- Refined color scheme for better readability
- Optimized staff display for terminal width compatibility

### Fixed
- Staff alignment issues when notes appear/disappear
- Chord text positioning and centering
- Layout shifting when chord names are displayed
- Bass and Treble clef horizontal alignment
- Rich markup errors when displaying multiple notes
- Consistent width maintenance across empty and note-filled staffs

## [0.1.0] - Initial Release

### Added
- **Config Mode**: MIDI device selection and configuration
- **Piano Mode**: Real-time visual 3-octave piano keyboard
  - Note highlighting in red
  - Real-time MIDI input processing
- **Chord Compendium**: Reference library of chords
  - All 12 musical keys
  - 15+ chord types per key
  - Chord note display
- **Chord Detection**: Automatic recognition of played chords
  - Support for basic triads (major, minor, diminished, augmented)
  - Extended chords (7th, 9th, 11th, 13th)
  - Suspended and added tone chords
- **MIDI Support**:
  - Cross-platform MIDI device detection
  - Real-time MIDI input handling
  - Device configuration persistence
- **TUI Framework**: Built with Textual
  - Keyboard navigation
  - Tab-based mode switching
  - Quit confirmation dialog
  - Responsive terminal layout

### Technical Stack
- Python 3.8+
- Textual (TUI framework)
- mido (MIDI I/O)
- python-rtmidi (Real-time MIDI backend)
- mingus (Music theory)

---

## Release Notes

### Version 1.0.0 - Major Milestone
This release represents a major milestone with the addition of traditional musical staff notation. The application now provides a complete visual experience combining:
- ASCII piano keyboard visualization
- Real-time chord detection and display
- Traditional music notation with Bass and Treble clefs

The side-by-side clef layout follows the standard grand staff convention used in piano sheet music, making it intuitive for musicians to read their playing in standard notation.

### Future Considerations
Potential areas for future enhancement:
- Recording and playback functionality
- MIDI file import/export
- Customizable key ranges
- Additional clefs (Alto, Tenor)
- Ledger lines for notes outside staff range
- Note duration display
- Metronome integration
- Multiple simultaneous MIDI device support
