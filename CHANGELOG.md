# Changelog

All notable changes to the Acordes MIDI Piano TUI Application will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.10.2] - 2026-03-26 - Scope: Desktop Visualizer

### Added

**Desktop Visualizer Window** (Windows, macOS, and Linux):
- New visual monitoring window for real-time audio analysis in Synth Mode
- Triggered via `v` keybinding (desktop versions only; silently disabled on Raspberry Pi/OStra)
- Fullscreen toggle via `f` keybinding with nearest-neighbor scaling, aspect-ratio preservation, and pure black background
- **VU Meter mode**: Dual asymmetric smoothing (fast attack 0.6, slow release 0.88) with color gradient (yellow → orange → red) mapped to dB scale (-48 to 0 dBFS)
- **Oscilloscope mode**: Zero-crossing triggered waveform display with phosphor-green anti-aliased line rendering, 512-sample window at 60 FPS
- Tab key cycles between visual modes
- Window positioning persistent across sessions (saved to `visualizer/window_position.json`)
- **Platform implementation**:
  - **Windows**: Uses Win32 API (SetWindowLongW/SetWindowPos) for always-on-top and drag-to-move
  - **Linux desktop**: Uses wmctrl subprocess calls for always-on-top and X11 window positioning (requires `wmctrl` package, typically `apt install wmctrl`)
  - **macOS**: Window opens and cycles modes fully; always-on-top and drag not supported without pyobjc dependency
  - **Raspberry Pi/OStra (ARM Linux)**: Visualizer silently disabled; all synth features unaffected

**Shared Memory IPC**:
- Lightweight per-buffer data flow: audio callback → shared memory → 30 Hz Textual timer → visualizer process
- Real-time waveform circular buffer (2048-sample, f32) for oscilloscope triggering
- NaN sentinel for clean shutdown coordination

### Changed

- Renamed `visualizer/vumeter_window.py` → `visualizer/visualizer_window.py` to reflect multi-mode architecture
- Synth Mode subprocess launch now detaches cleanly on all platforms (Win32 `DETACHED_PROCESS`, Unix `start_new_session=True`)
- Updated fonts to Silkscreen from arm_ui/fonts (pixel-perfect rendering at 6-8pt)

### Technical Notes

- Visualizer window runs as a separate pygame subprocess with no console attachment
- Always-on-top implemented via platform-native window managers (Win32, wmctrl on Linux)
- Asymmetric smoothing on VU meter creates responsive peak response while smooth decay for musical feel
- dB-to-bar conversion uses 20log10(level) with DB_MIN=-48 and DB_MAX=0 (dBFS)
- Zero-crossing trigger finds stable display point in waveform buffer to prevent flicker
- Crossfading rendered surfaces to nearest-neighbor scaling eliminates anti-aliasing artifacts in fullscreen

---

## [1.10.1] - 2026-03-26 - Grasp Refinement: RAM Pre-Allocation, TPDF Dithering & Performance Tuning

### Added

**Three-tier RAM pre-allocation** (zero hot-path allocations):
- **Tier 1**: Per-voice pre-allocated buffers for waveform generation, envelope sampling, filter processing, DC blocking, and onset ramping. All stored in `Voice.__init__` and reused every buffer cycle
- **Tier 2**: Pre-allocated ring-buffer index arrays for chorus and delay write-position computation (eliminates `.astype(np.int32)` allocations)
- **Tier 3**: Shared ramp buffer and allocation-free `_fill_linspace()` helper for all parameter ramps (filter sweeps, mute ramps, crossfades). In-place `np.clip` for final output normalization

Performance result: 8-voice polyphony 4.336ms per buffer (benchmarked with stream stopped to eliminate PyAudio thread overhead), near the original 3.975ms baseline. Correctness verified across all waveforms (SAW, PULSE, TRI, SINE) and filter types.

**TPDF triangular PDF dithering**:
- Implements Chris Johnson's airwindows architecture: independent per-channel RNG states (NumPy PCG64 seeded 0xACC05000 / 0xACC05001)
- Triangular distribution (r1 - r2) applied before float32→int16 conversion for quantization noise shaping
- Improves noise floor consistency across both channels without inter-channel correlation
- Zero runtime cost: dither generation overlaps with filter-to-output processing

**Output gain optimization**:
- Added +3 dB pre-saturation makeup gain to fill unused headroom from conservative per-voice normalization
- Single voices now output at -3.6 dBFS (vs. previous -8 dBFS), giving the synth more "juice" at typical playing levels
- Transparent optimization: high-drive presets are unaffected (tanh already saturates fully at drive ≥ 2.0)
- Maintains soft-clipper saturation character while increasing perceived loudness without additional DSP cost

### Fixed

- **Key Tracking Parameter**: Parameter updates were silently dropped due to missing `self.key_tracking` attribute sentinel in `hasattr()` guard. Added `self.key_tracking = 0.5` to enable proper queue dispatch and smooth 90ms parameter ramping. Now fully responsive (0-100% range).
- **Performance regression from pre-allocation**: Eliminated overhead from `hasattr()` checks in `_apply_dc_blocker`, inlined envelope times computation, and made `_sanitize_signal` fully in-place with `nan_to_num`

### Changed

- `music/synth_engine.py`: Added `_MAKEUP_GAIN = 1.4`, TPDF dithering state/buffers, pre-allocated voice buffers and engine-level index/ramp arrays, allocation-free `_fill_linspace()` helper, all waveform/envelope/filter methods updated with optional `_out`/`_phases` parameters for pre-allocated buffers. Hot path passes buffers explicitly to eliminate allocation overhead

---

## [1.10.0] - 2026-03-25 - Grasp: Polyphonic Voice Stealing Refinement

### Added

**Ghost voice system (POLY mode)**:
- New overflow voice pool (2 slots on desktop, 1 on ARM) that captures release tails from stolen voices
- When a POLY voice must be stolen while still audible (envelope > 5%), its full state (phase, filter memory, DC blocker, envelope position) is promoted to a ghost slot
- The real slot is freed immediately for the new note with a clean filter state, preventing frequency-domain glitches
- Ghost voices output at reduced gain (0.7×) and are never counted in gain normalisation
- Ghost slots auto-reclaim when their release envelope fully decays
- Three-tier steal priority: (1) safe steal of near-silent releasing voices, (2) ghost promotion for still-audible tails, (3) brutal steal if all slots full (rare)

**ARM filter upgrade (4-pole cascade)**:
- Replaced single 2nd-order biquad (12dB/oct) with two cascaded biquad sections (4-pole, 24dB/oct)
- Stage 1 carries resonance peak (Q scales 0.707→12 with resonance), Stage 2 near-Butterworth (Q 0.707→1.2 for stability)
- Asymmetric Q distribution prevents runaway instability while maintaining warm Moog-like character
- All changes use `scipy.sosfilt` (C code, GIL-free) so ARM performance remains untouched
- Matches desktop Moog ladder rolloff slope for perceptually consistent filter character across platforms

### Fixed

- POLY voice stealing now preserves audible release tails instead of brutally cutting them, eliminating tail artifacts during rapid note playing
- Simulation tool confirms zero buffer-boundary glitches across all voice modes (MONO/UNISON/POLY sequential and overlapping scenarios)

### Changed

- `music/synth_engine.py`: Added ghost voice pool, three-tier POLY steal logic, 4-pole ARM LPF cascade
- `tools/simulate_octave.py`: Headless synth simulation tool with full octave playback, glitch detection, and waveform visualization

---

## [1.9.3] - 2026-03-25

### Fixed

**MONO/UNISON voice stealing artifacts (major overhaul)**:
- Removed `_mono_dissolve_gain` normalization: the 1/sqrt(2) per-voice scale was snapping the
  old voice down 29% at every steal and snapping back up ~41% 150ms later, both audible as clicks
- Filter delay-line states (ladder, SVF, DC blocker) no longer inherited on voice steal: stale
  frequency-mismatch energy at high resonance (Q≈9) rang as ghost tones on pure-sine waveforms
- Pre-gate S-curve now inherits `pre_gate_progress` from the outgoing voice instead of resetting
  to 0.0: rapid re-triggers (key bounce, half-pressed keys) no longer dip to silence and stutter
- Stolen voice release capped at 15ms (new `Voice.release_time_cap`) regardless of the release
  knob: prevents two simultaneous pure-sine voices from beating long enough to produce audible AM
- Filter coefficient smoothers (`smooth_fl_lpf/hpf`, `smooth_resonance`) still inherited to prevent
  sudden cutoff jumps from key tracking or FEG position at the steal moment
- Phase continuity maintained on steal: new voice starts at old voice's phase to prevent
  destructive interference during the dissolve overlap

**Sample rate and scipy improvements**:
- Sample rate exposed via `ACORDES_SAMPLE_RATE` env var for rapid testing without code changes
- `scipy.lfilter` DC blocker fast path extended to all platforms (zero quality trade-off, ~100x speedup)
- `scipy.sosfilt` Moog ladder replacement correctly guarded as ARM-only (was accidentally extended
  to desktop in a prior session, causing quality regression)

**Config mode**:
- Oversampling toggle vertical size fixed: no longer shifts the screen or causes scroll overlap

### Changed

- `music/synth_engine.py`: MONO/UNISON voice steal rewrite, sample rate env var, scipy guards,
  `_TRANSITION_XF_SAMPLES` raised from 8 to 48 samples (1.1ms), `Voice.release_time_cap` field
- `modes/config_mode.py`: Oversampling toggle layout fix

## [1.9.2] - 2026-03-10

### Added

**MIDI CC Mapping System**:
- 16 assignable MIDI CC knobs organized as 4 banks of 4 knobs each
- Configuration file `midi/cc_mappings.json` stores CC-to-parameter mappings with min/max ranges
- Bank 1 pre-configured: CC 74 (cutoff), CC 71 (resonance), CC 75 (wave blend), CC 7 (master volume)
- Banks 2-4 for effects, envelope, LFO, arpeggiator parameters (easily customizable)

**CC 75 Smart Focus Control**:
- CC 75 in focus mode controls the currently highlighted parameter dynamically
- Supports continuous parameters (with log scaling for frequencies)
- Supports discrete lists (waveforms, filter routing, LFO shapes, arpeggiator modes, voice type)
- Supports discrete ranges (octave, chorus voices, arpeggiator range)
- Section-aware parameter lookup resolves naming conflicts (LFO Depth vs Chorus Depth, etc.)

**Noise Engine Improvements**:
- Switched from white noise to pink noise (1/f spectrum, warmer and more musical character)
- Noise blended pre-filter so the VCF shapes it alongside the tone (analog synth behavior)
- Square-root curve on noise blend level (0.25 gain multiplier) keeps low values subtle
- Full gain sweep across 0-100% feels musical instead of harsh threshold at ~10%

**Filter Responsiveness**:
- Engine-level resonance smoothing: 0.94 → 0.0 (instant; per-voice smooth handles artifacts)
- HPF resonance smoothing: 0.90 → 0.50 (fast 3-buffer ramp, ~32ms)
- HPF Q range: 0.5-4.0 → 0.5-10.0 (matches LP filter range)
- Fixes weak HP peak in MS-20 HP+LP routing when both resonances are high

### Changed

- `modes/synth_mode.py`: Added CC mapping system with section-aware parameter lookup
- `music/synth_engine.py`: Pink noise pre-filter blending, optimized filter smoothing
- `midi/cc_mappings.json`: New configuration file for MIDI CC assignments (user-customizable)
- README.md: Added MIDI CC mapping documentation and v1.9.2 release notes

### Fixed

- Resolved parameter name ambiguity in focus mode (same label in different sections)
- Corrected chorus_voices range (1-4, not 2-8) and arpeggiator on/off toggle state
- Filter resonance now feels responsive (no stacked smoothing stages slowing changes)
- Noise no longer harsh above 10% (pre-filter + pink spectrum + sqrt curve fix)

## [1.9.1] - 2026-03-09

### Changed

- Synth engine parameter accuracy: FIR cutoff, ladder alpha, SVF Q stability improvements
- Gain staging refinements: octave compensation for perceived loudness, POLY gain fix
- Filter resonance layer optimization: removed double-smoothing deadzone
- HPF Q range increased, Peak scale changed from percentage to 0-10 display

## [1.8.9] - 2026-03-07

### Added

**Audio Output Device Selection**:
- Added audio device selection to Config Mode (new third section: Audio Output)
- TAB now cycles through three lists: MIDI Input → Audio Output → Velocity Curve
- Three built-in options always available:
  - **System Default**: Lets OS/PipeWire route to active speakers (recommended for Linux/KDE/PipeWire)
  - **No Audio**: Engine runs silently; useful for browsing compendium mode, metronome, etc. without sound
  - **Hardware Devices**: Enumerate specific PyAudio devices (Windows/macOS/Linux)
- On first launch (no saved audio device), app shows Config Mode before starting audio engine
- User must select audio device before engine initializes
- On subsequent launches, saved audio device index is used automatically
- Fixes Linux/ALSA sound card selection issues (Fedora, Ubuntu, etc.)
- Subtitle displays both MIDI device and current audio output (e.g., `🎹 USB Keyboard | 🔊 System Default`)

**Audio Device Deduplication** (`music/synth_engine.py`):
- Windows: PyAudio lists same physical device multiple times (once per host API: MME, DirectSound, WASAPI, WDM-KS)
- New `list_output_devices()` deduplicates by device name, preferring WASAPI for best latency
- Cleans up device list to show one entry per unique device

**Engine Startup Deferral & Device Validation** (`main.py`):
- Audio engine (`SynthEngineProxy`) is now lazily initialized
- On first launch: waits for user to select audio device in Config Mode before starting
- On subsequent launches: validates that saved audio device is still present in system
  - If saved device is gone (e.g. USB interface unplugged), automatically clears saved config
  - Routes user to Config Mode to select a new device (e.g. fallback to built-in speakers)
  - User never faces errors from missing/invalid audio devices
- Improves startup flow and ensures reliable audio device configuration on every launch

**Launcher Improvements** (`run.sh`):
- Cleaner output: `uv sync` runs silently on success, verbose output only on failure
- Improved PATH handling: early export of `~/.local/bin` and `~/.cargo/bin` for uv detection
- Better error messages for dependency installation failures

### Changed

- `config_manager.py`: Added `audio_device_index` and `audio_device_name` persistence
- `music/engine_proxy.py`: Added `restart_with_device()` method to switch audio device mid-session
- `modes/config_mode.py`: Complete rewrite with Audio Output Device section, 3-way TAB cycling
- `main.py`: Restructured startup flow to defer engine creation until audio device is chosen

## [1.8.8] - 2026-03-07

### Fixed

**Synth Mode Focus Persistence**:
- Added parameter focus state tracking: focus mode now remembers the last accessed parameter when re-entering
- First entry defaults to OSCILLATOR - Wave, subsequent entries return to last position
- Implemented `_last_focus_section` and `_last_focus_param` state variables in `modes/synth_mode.py`
- Focus position saved when exiting focus mode, restored when re-entering

**Config Mode Usability**:
- Fixed TAB key to toggle focus between MIDI device and velocity curve lists instead of moving forward
- Removed Shift+TAB shortcut for clarity
- Auto-highlights active device/curve when switching focus between lists
- Improved visual feedback when toggling between lists

**Application Launch Flow**:
- Fixed black screen when user exits config mode without selecting a MIDI device
- Restructured `_after_engine_ready()` to always push MainScreen first, then optionally ConfigMode on top
- Ensures main menu is visible when config mode is dismissed via Escape
- Callback now properly reconnects MIDI device if user selected one in config

**Parameter Naming**:
- Fixed parameter name in Tambor mode: `arpeggiator_enabled` changed to `arp_enabled` for consistency

## [1.8.6] - 2026-03-07

### Fixed

**Chord Detection**:
- Fixed chord detection with enharmonic equivalents (Eb, Bb, etc.) in `music/chord_library.py`
- Added `ENHARMONIC_MAP` and `_normalize_note()` to normalize flats to sharps before comparison
- C Minor now correctly detected when C, Eb, G notes are played (was incorrectly showing C-D#-G)

**Audio Engine**:
- Increased startup silence buffer from 50ms to 1 second in `music/synth_engine.py`
- Eliminates audio click/artifact at application startup by allowing filter and oscillator states to settle

**UI Fixes**:
- Fixed MarkupError in `main.py` SynthHelpBar: escaped literal `[/]` text to prevent Rich markup parsing
- Applied user's manual synth_mode.py parameter label expansions (Atk→Attack, Dcy→Decay, etc.)

**Performance Optimizations**:
- `components/piano_widget.py`: Fixed redundant regex execution on every render by caching cleaned lines alongside border width
- `components/staff_widget.py`: Optimized note placement to avoid multiple list conversions per staff line

**Linux Setup**:
- `run.sh`: Added automatic installation of `uv`, Python 3.12, and system audio dependencies
- Detects package manager (dnf/apt/pacman/brew) and installs portaudio-devel, python3-devel, gcc
- `README.md`: Added setup instructions for making run.sh executable on first clone

**Compendium Mode Audio**:
- Fixed timer leak causing UI lag and audio artifacts when changing chords (`modes/compendium_mode.py`)
- Added `_cancel_play_timers()` and `_playing_notes` tracking to prevent stale note-on/off calls
- Implemented audio crossfade: old chord releases naturally (via `note_off`) while new chord attacks simultaneously
- Set smooth ADSR envelopes for compendium: attack=0.06 (60ms fade-in), release=0.55 (550ms fade-out)
- Eliminates clicks and ensures chord transitions are musically smooth

## [1.8.5] - 2026-03-06

### Added

**Filter Character & Analog Warmth**:
- **Per-Stage Ladder Saturation** (`music/synth_engine.py`):
  - Added `math.tanh()` saturation at each of the 4 integrator stages in the Moog ladder filter
  - Gain compensation (1.1× scaling) restores unity output level for clean signals at drive=1.0
  - Produces rich even harmonics when driven hard, matches hardware Moog character
  - Transforms linear filter into soft, continuous saturation curve across all resonance values

- **Filter Drive Parameter** (0.5–8.0× multiplier):
  - Pre-filter gain control in `synth_engine.py`: `filter_drive_current/target/smoothing` with 0.85 smoothing coefficient
  - Applied in `_apply_filter()` before ladder input
  - New UI control in Oscillator section: "Drive" knob (adjustable 0.1 steps via Q/E)
  - Maps directly to filter saturation intensity; 1.0 = clean/neutral
  - Persisted in presets via `preset_manager.py` DEFAULT_PARAMS

- **SVF Soft Saturation** (replacing hard clamps):
  - `_filter_svf_hp_process()` and `_filter_svf_process()`: Replaced hard clamps (if lp > 4.0) with `math.tanh(lp * 0.25) * 4.0`
  - Applied to lp and bp integrator states; hp naturally bounded by bp saturation
  - Smoother, more analog saturation vs. digital-sounding hard clipping
  - Same saturation limits (±4.0, ±8.0) prevent state blowup

- **Filter Routing Modes** (4 SVF→Ladder topologies):
  - `_filter_svf_hp_process()`: Added `routing` parameter to select output
  - Four modes: "lp_hp" (default MS-20: SVF HP→Ladder LP), "bp_lp" (SVF BP→Ladder), "notch_lp" (SVF Notch→Ladder), "lp_lp" (dual LP)
  - Notch computed as `input - lp` per Chamberlin formula
  - New UI control in Filter section: "Route" selector (cycle via Q/E)
  - Persisted in presets as `filter_routing` parameter

- **Thermal Noise Floor**:
  - Inaudible (-100 dBFS) random noise injection in `_apply_filter()` before ladder
  - `np.random.randn() * 1e-5` prevents filter dead-zone lock during self-oscillation
  - Adds subtle analog "air" texture inaudible in isolation but felt in the mix
  - Always-on (no parameter), unaffected by drive/resonance settings

**Patch Management**:
- **Init Patch** (`action_init_patch()` via "i" key):
  - Resets to clean starting point: pure_sine waveform, oct 0, filters wide open (20 Hz HPF, 20 kHz LPF)
  - Disables all FX (no chorus/delay), no modulation (LFO depth=0), ADSR 10ms/200ms/70%/300ms
  - Sets filter_drive=1.0 (clean), filter_routing="lp_hp" (default), voice_type="poly"
  - Sends mute gate before reset, marks as unsaved (no preset name persisted)
  - `_INIT_PATCH` constant dict contains all 40 parameters for reproducibility

- **Reset Focused Parameter** (`action_reset_focused_param()` via "r" key in focus mode):
  - Resets only the currently highlighted parameter to its init value from `_INIT_PATCH`
  - Works in all sections (Oscillator, Filter, Amp EG, Filter EG, LFO, Chorus, FX, Arpeggio, Mixer)
  - Updates display widget immediately, marks dirty, auto-saves
  - Shows notification: "{ParamName} → init"
  - Silently ignored when not in focus mode

**UI & Help Bar**:
- Updated `SynthHelpBar` in `main.py` to display "R: Reset" and "I: Init" shortcuts
- Reorganized help bar into two logical lines: focus controls, preset/volume/saving, panic/randomize
- Moved Key Tracking from Filter section to Amp EG section for better parameter organization
- Removed horizontal divider lines from Oscillator section

### Technical Details

**Files Modified**:
- `music/synth_engine.py`: Added `import math`; filter saturation, drive, routing, thermal noise
- `modes/synth_mode.py`: New section params, state vars, adjusters, formatters, reset logic, init patch dict, help bar
- `music/preset_manager.py`: Added `filter_drive` and `filter_routing` to DEFAULT_PARAMS
- `main.py`: Updated VERSION to "1.8.5", updated SynthHelpBar display

**Parameter Changes**:
- Engine: `filter_drive_current/target/smoothing`, `filter_routing` (string enum: "lp_hp"|"bp_lp"|"notch_lp"|"lp_lp")
- UI: Added state: `self.filter_drive`, `self.filter_routing`; widgets: `filter_drive_display`, `filter_routing_display`
- Presets: 40 parameters now include `filter_drive` (default 1.0) and `filter_routing` (default "lp_hp")

---

## [1.8.0] - 2026-03-05

### Changed
- **Launcher Scripts Optimization**: Silent, efficient startup
  - `run.ps1` and `run.sh` now detect cached setup (`.python-version` and `.venv` files) and skip setup output on subsequent runs
  - Only prints progress when doing actual work (first setup, missing dependencies, or errors)
  - Subsequent runs launch the app silently with zero unnecessary output
  - Error messages remain clear and helpful for troubleshooting

- **uv Integration Complete**: Cross-platform Python & dependency management
  - `pyproject.toml` created (PEP 517 compliant, no build-system needed for script apps)
  - `uv python pin` ensures Python 3.12/3.11 availability (auto-installs if needed)
  - `uv sync` replaces pip for fast, reliable dependency installation
  - `.python-version` file persists Python selection across runs
  - Works identically on Windows, Linux, and macOS

### Fixed
- **pyproject.toml Warnings**: Removed invalid `[tool.uv]` section that was causing TOML parse warnings

---

## [1.7.9] - 2026-03-05

### Added
- **uv Project Configuration** (`pyproject.toml`): Professional Python project setup
  - `pyproject.toml` defines project metadata, dependencies, and build configuration
  - Enables `uv sync` for fast, reliable dependency installation across all platforms
  - Python requirement pinned to 3.11+ (compatible with PyAudio/python-rtmidi wheels)
  - Project metadata includes version, description, keywords, and author info

- **Velocity Curves**: Five configurable MIDI velocity response curves to control dynamic sensitivity
  - **Linear**: 1:1 identity mapping (no remapping)
  - **Soft**: √ compression curve (gentle playing triggers fuller volume)
  - **Normal**: 50/50 blend of linear + soft (balanced, all-around response)
  - **Strong**: Power 1.8 exponential (must play harder to reach full output)
  - **Very Strong**: Power 3.0 aggressive exponential (quiet = nearly silent)
  - Selectable in Config Mode, applied globally to all MIDI input
  - Lookup-table driven (`music/velocity_curves.py`) for zero CPU overhead
  - Thread-safe remapping in MIDI input handler before callbacks fire

### Changed
- **Config Mode UI**: Expanded to include velocity curve selector below MIDI device list
  - Two-section layout: MIDI Devices (top) and Velocity Curves (bottom)
  - Tab/Shift+Tab navigation between sections
  - Space to select curve
  - Curves saved to config.json and restored on restart

### Technical
- New module: `music/velocity_curves.py` with 5 pre-built 128-entry lookup tables
- `midi/input_handler.py`: Now accepts optional `config_manager` parameter in `__init__`
- Velocity remapping applied in `_handle_note_on()` before callbacks fire
- All modes (Piano, Synth, Compendium, Tambor) automatically receive curve-adjusted velocities

---

## [1.7.8] - 2026-03-04

### Changed
- **Project Organization**: Cleanup of excess development documentation
  - Removed 9 planning/development markdown files (ARTIFACT_ELIMINATION_TEST.md, AUDIO_THREADING_PLAN.md, COMPENDIUM_*.md, PRESET_BROWSER_*.md, SYNTH_SUBPROCESS_DESIGN.md, TEST_PRESET_BROWSER.md)
  - Removed requirements-windows.txt (outdated stub)
  - Removed run.bat (Windows CMD launcher;use run.ps1 instead)

- **Documentation Reorganization**:
  - **README.md**: Cleaner structure with broad project overview, architecture, and quick-start guide
    - Removed version history (moved to CHANGELOG.md)
    - Removed keyboard shortcut list (moved to KEYBINDS.md)
    - Removed command-line launcher references (PowerShell/Linux/macOS only)
  - **KEYBINDS.md**: New comprehensive keyboard shortcut reference for all modes and features
  - **CHANGELOG.md**: Now contains complete version history with technical details

---

## [1.7.7] - 2026-03-01

### Fixed
- **Focus-Mode Acceleration**: Time-based exponential parameter adjustment
  - Acceleration dead zone: 1000 ms (no multiplier)
  - Time constant: 2500 ms (reaches 2× speed after extended hold)
  - Max cap: 2× multiplier (slow, musical growth)
  - Percentage parameters: 0.01 (1%) per single tap
  - Works across all parameter types (additive, multiplicative, knob-style)

- **EG Parameter Minimums & Resonance Caps**:
  - Attack minimum: 8 ms (was 1 ms;prevents hard transients)
  - Decay minimum: 5 ms (was 1 ms)
  - Release minimum: 8 ms (was 1 ms)
  - Filter Resonance max: 0.80 (was 0.90;eliminates self-oscillation artifacts)
  - HPF Resonance max: 0.85 (was 0.99)
  - All clamped on preset load in `_apply_params()`

- **Parameter Display Accuracy**:
  - `_fmt_time()`: Log-scale bounds updated to [5ms, 5s] (was [1ms, 5s])
  - `_fmt_resonance()`: Divides by 0.80 (was 0.90)
  - `_fmt_hpf_resonance()`: Divides by 0.85 (was 0.99)
  - Slider fills now accurately reflect new min/max ranges

- **Parameter Persistence Bug**:
  - `_load_initial_params()` was loading preset only, ignoring synth_state
  - Fixed to layer: defaults → preset → synth_state (synth_state now takes priority)
  - CHORUS/FX mix values now correctly restored on app restart

---

## [1.7.0] - 2026-03-03

### Added
- **Complete Artifact Elimination on Note Transitions**: 12/12 CLEAN test results on all MONO/UNISON transitions
  - Engine-level post-tanh 8-sample crossfade for exact sample-0 continuity
  - 100% deterministic testing with race condition fix for PyAudio background thread coordination
  - No clicks, no glitches, no discontinuities during rapid note changes

### Fixed
- **Test Race Condition**: PyAudio background thread now properly coordinated with direct test callback calls
  - `test_artifact_analysis.py` now stops audio stream before running tests
  - Eliminates non-deterministic MIDI event draining and state consumption
  - All 12 test cases now pass consistently across multiple runs

### Technical Details
- **Crossfade mechanism** (`synth_engine.py` lines ~1584-1597):
  - Applies post-saturation (after tanh soft-clip) for accurate output continuity
  - Uses `_last_output_L/R` (previous buffer's final post-tanh sample)
  - Linearly fades 8 samples at 48kHz (~0.167ms) from old to new output
  - Sample-accurate timing, zero glitches

## [1.6.0] - 2026-02-26

### Added
- **Compendium Search Functionality**: Real-time search across all 258+ music items
  - Search input at top of Compendium Mode;filters tree on every keystroke
  - Searches all fields: name, description, details, examples, metadata (case-insensitive)
  - Results grouped by category (Chords, Scales, Modes, Instruments, Genres) with item counts
  - Existing chord auto-play and detail panel work seamlessly with search results
  - Tab/Shift+Tab focus cycling between search input and tree
  - Delete search text to instantly restore full hierarchical tree
  - `CompendiumDataManager.search_items()` method for flexible querying
  - `CompendiumMode._build_search_results_tree()` for organized result display
  - `on_input_changed()` event handler for real-time filtering

- **Music Modes Category (NEW)**: 7 diatonic modes with complete theory
  - Ionian (1st degree);Major scale equivalent
  - Dorian (2nd degree);Jazzy, funky, groovy minor
  - Phrygian (3rd degree);Dark, exotic, Spanish/flamenco
  - Lydian (4th degree);Ethereal, dreamy, bright
  - Mixolydian (5th degree);Major with bluesy quality
  - Aeolian (6th degree);Natural minor (sad, introspective)
  - Locrian (7th degree);Very dark, dissonant, unstable
  - Each mode includes intervals, semitones, usage, and related modes
  - New `data/compendium/modes.json` file with 7 modal entries

- **Expanded Instruments (6 → 28 items)**:
  - String Instruments family (10): Piano, Guitar, Violin, Cello, Viola, Double Bass, Harp, Mandolin, Ukulele, Bass
  - Brass Instruments family (4): Trumpet, French Horn, Trombone, Tuba
  - Woodwind Instruments family (4): Saxophone, Clarinet, Flute, Oboe
  - Percussion family (1): Drums
  - Keyboard Instruments family (3): Organ, Synthesizer
  - Vocal Instruments family (1): Vocals
  - Hierarchical tree organization with family grouping in Compendium display
  - Each instrument includes range, polyphony, learning curve, artist examples, metadata

- **Expanded Genres (6 → 22 items)**:
  - Original 6: Jazz, Blues, Rock, Classical, Pop, Hip Hop / Rap
  - Added 16: Country, Folk, Reggae, Electronic / EDM, Metal, R&B / Soul, Funk, Latin / Salsa, Gospel, Ambient, Indie / Alternative, Punk, Disco, World / Ethnic Music, Ska, Grunge
  - Each genre includes era, origin, characteristics, instruments, subgenres

- **Expanded Scales (7 → 15 items)**:
  - Original 7: Major, Natural Minor, Harmonic Minor, Melodic Minor, Major/Minor Pentatonic, Blues
  - Added 8 exotic scales: Harmonic Major, Whole Tone, Phrygian Dominant, Diminished (Octatonic), Augmented, Altered (Super Locrian), Mixolydian Flat 6 (Hindu), Neapolitan Minor
  - Comprehensive intervals, semitone patterns, and usage information

- **Improved Compendium Category Hierarchy**:
  - Updated `data/compendium/categories.json` to include Modes as 6th main category under Music
  - All 258+ items organized across 6 categories with cross-references

### Changed
- `ENABLE_COMMAND_PALETTE = False` in `AcordesApp` class (`main.py`);Textual command palette disabled for cleaner interface
- Version updated from 1.5.0 → 1.6.0 in `main.py` and documentation
- **Header title no longer expands on click**: Disabled Textual Header expand behavior via `can_focus=False`, `expand=False`, and `action_toggle_header()` override for cleaner UI
- **Category descriptions in Compendium**: Selecting major categories (Chords, Scales, Modes, Instruments, Genres) now displays category description and subcategories in detail panel
- **Fixed category icons in full tree**: Category nodes now display correct icons (🎹 🎧 📊 🎼 🎸) in full tree view, matching search results

### Architecture Notes
- Search implementation is non-destructive;existing tree building methods unchanged
- Search is real-time via `Input.Changed` event handler;no Enter key needed
- Substring matching (not fuzzy) for predictable, responsive filtering
- Instrument hierarchy created via `_build_instruments_tree()` method recognizing family category nodes
- All existing features (detail panel, auto-play, navigation) work unchanged with search results
- Data validation test (`test_compendium_data.py`) updated to handle categories.json different structure
- Fully backward compatible;old presets and saved state load correctly

---

## [Tambor Drum Machine] - 2026-02-26

### Features
- **Drum Machine Mode (Mode 5)**: 16-step sequencer with 8 drum sounds (Kick, Snare, Hi-Hats, Clap, Toms)
  - 64 pattern slots with JSON persistence
  - 16 pre-defined fill patterns with dynamic expansion
  - Pattern editing, mute/solo controls, humanization, timing modes (straight/swing/shuffle)
  - Pre-scale note filtering for drum tweaking
  - BPM synchronization across all application modes

### Fixed
- **Adjacent Drum Steps Glitching**: Removed blocking note_off() call before note_on(), allowing smooth voice retriggering when drums trigger consecutively
- **Multi-Drum Mixing Artifacts**: Per-MIDI-note parameter caching prevents parameter overwriting when multiple drums trigger on the same step
- **BPM Synchronization**: Proper cleanup in on_unmount() ensures BPM stays synchronized between Tambor, Metronome, and other modes
- **Performance Issues**: Pink noise CPU usage optimized by 87% (15% → 2%) using Voss-McCartney algorithm
- **Parameter Editing Glitches**: Removed real-time synth updates from drum editor, preventing audio artifacts during parameter adjustment
- **Mode Switching Crashes**: Fixed AttributeError in timer cleanup by using .stop() on Timer objects instead of non-existent remove_timer()
- **BPM Display Desync**: Control panel now reads BPM from config_manager, staying synchronized when switching between modes

### Technical Improvements
- **Monophonic Drum Voices**: 8 pre-allocated voices (0-7) with one drum per voice, preventing polyphony and voice-stealing artifacts
- **Percussion-Optimized Parameters**: Fast attack (0.2-3ms), decay (70-300ms), zero sustain, short release (15-50ms)
- **Noise Generation**: White noise for hi-hats/snares, pink noise for kick drums
- **DrumVoiceManager Class**: Manages drum voice allocation, parameter application, and triggering
- **Event Queue Integration**: Parameters enqueued per-note for proper audio thread synchronization

## [1.5.0] - 2026-02-19

### Added
- **LFO shape & target routing** (`music/synth_engine.py`, `modes/synth_mode.py`): LFO section upgraded from a single sine modulator to a full 4-shape, 4-target modulation bus.
  - Shapes: **SIN** (sine), **TRI** (triangle), **SQR** (square), **S&H** (sample & hold;latches a new random value on each LFO period).
  - Targets: **ALL**, **VCO** (pitch), **VCF** (filter), **VCA** (amplitude). Target routing replaces the old per-destination `lfo_vco_mod` / `lfo_vcf_mod` / `lfo_vca_mod` manual sliders while retaining backward compat with old presets.
  - New params in `DEFAULT_PARAMS`: `lfo_shape`, `lfo_target`, `lfo_depth`.
  - Phase-wrap S&H detection: uses `lfo_phase_prev > lfo_phase` (valid because the max increment per buffer at 20 Hz is ~0.67 rad, well below 2π).
- **FX Delay** (`music/synth_engine.py`, `modes/synth_mode.py`): Stereo ping-pong echo with per-sample feedback loop.
  - Parameters: `delay_time` (50 ms – 2 s), `delay_feedback` (0 – 0.9), `delay_mix` (0 – 1 wet/dry).
  - Fully bypassed when `delay_mix == 0`;zero CPU cost when off.
  - **Rev Size** placeholder shown in UI (greyed out, labelled "future") to reserve UI space for a future reverb implementation.
- **BBD-style Chorus** (`music/synth_engine.py`, `modes/synth_mode.py`): Tape-emulation chorus with 1–4 modulated delay taps.
  - Parameters: `chorus_rate` (0.1 – 10 Hz), `chorus_depth` (0 – 1 → 0–25 ms sweep), `chorus_mix` (0 – 1 wet/dry), `chorus_voices` (1–4 taps, phases 90° apart).
  - Single shared ring buffer (30 ms); all taps read from different LFO-modulated offsets. Fully bypassed when `chorus_mix == 0`.
- **Arpeggiator** (`music/synth_engine.py`, `modes/synth_mode.py`, `config_manager.py`, `modes/metronome_mode.py`): Audio-callback-driven polyphonic arpeggiator with sample-accurate timing.
  - Modes: **UP**, **DOWN**, **UP+DOWN** (bounce), **RANDOM**.
  - Parameters: `arp_bpm` (50–300, shared with Metronome), `arp_gate` (5–100% note-on fraction), `arp_range` (1–4 octave span), `arp_enabled` (on/off toggle).
  - Step counter carries the remainder across buffer boundaries;no cumulative phase error.
  - BPM is stored in `config_manager` (not in presets) so Metronome and Arpeggiator always stay in sync.
- **Shared BPM** (`config_manager.py`, `modes/metronome_mode.py`, `main.py`): MetronomeMode now accepts `config_manager` as an optional constructor argument. BPM changes in Metronome write to `config_manager.set_bpm()`, and the Arpeggiator reads/writes the same key, so both modes share a single persistent BPM setting.

### Changed
- `SynthMode._SECTION_PARAMS["fx"]` updated: `["Delay Time", "Delay Fdbk", "Delay Mix", "Rev Size"]`.
- `SynthMode._SECTION_PARAMS["arpeggio"]` updated: added `"ON/OFF"` toggle row (5 params total).
- All four previously dummy sections (LFO, Chorus, FX, Arpeggio) are now fully interactive;every param is wired to the focus-navigation system (Enter → arrows → Q/W ± to adjust).
- `action_randomize` does NOT randomise the new FX / Chorus / Arp params;it only rolls dice on the core synthesis chain (waveform, octave, ADSR, filter), keeping effects settings stable between randomize presses.

## [1.4.3] - 2026-02-19

### Fixed
- **Low-frequency onset thump** (`music/synth_engine.py`): Sine waveform at octave=-2 with short attack produced an audible thump on note onset. Root cause: the DC blocker (coeff=0.999, pole at 2.4 Hz) has a ~66 ms settling time at 55 Hz, but the onset ramp was a fixed 3 ms;covering less than 1/6 of a 55 Hz cycle.
  - **Frequency-adaptive `ONSET_RAMP`**: Duration now computed as `max(3ms, min(30ms, 1.5 × period_ms))` per voice, stored in `voice.onset_ms` set at trigger time. At 55 Hz: 27 ms; at 440 Hz: 3 ms (unchanged;no regression at mid/high frequencies).
  - **Frequency-adaptive `ANTI_I`**: Envelope soft-start window in `_apply_envelope` now reads `voice.onset_ms / 1000.0` instead of the hardcoded 5 ms constant, matching the onset ramp duration so the exponential attenuation covers the DC blocker's full settling window.
  - **Adaptive DC blocker coefficient** (`_apply_dc_blocker`): Coefficient is now computed per-voice based on `voice.frequency`;`0.9990` above 100 Hz (pole 2.4 Hz, standard behaviour), linearly interpolated to `0.9997` below 50 Hz (pole ≈ 0.7 Hz). This reduces phase distortion at very low fundamentals; combined with the longer onset ramp, the onset transient is fully hidden.
- **Randomize click on held notes** (`music/synth_engine.py`, `modes/synth_mode.py`): Pressing `-` (randomize) while a note was held caused an audible click because `waveform`, `octave`, and envelope parameters (`attack`, `decay`, `sustain`, `release`) were applied via `setattr` instantly on the next audio buffer;creating mid-note frequency, waveshape, and amplitude discontinuities.
  - **Output mute gate** (`_mute_ramp_remaining` / `_mute_ramp_fadein` / `_MUTE_RAMP_LEN=384`): A new `'mute_gate'` event type arms a ~8 ms (384-sample) fade-out ramp on the mixed output. When the fade-out completes, a matching fade-in is automatically queued. Both the `mute_gate` and `param_update` events are drained in the same `_process_midi_events()` call, so the new params are applied under silence and the fade-in plays with the new waveform/octave already active.
  - `action_randomize` now enqueues `{'type': 'mute_gate'}` before `_push_params_to_engine()` so the gate is always armed before any parameter changes land on the audio thread.

## [1.4.2] - 2026-02-19

### Changed
- **Synth Mode focus navigation overhaul** (`modes/synth_mode.py`):
  - Up/Down arrows now cross section row boundaries;pressing Up at the first param of a section jumps to the last param of the same column in the adjacent row. All 8 sections (including LFO, Chorus, FX, Arpeggio) are reachable without mouse.
  - Added **Alt+Left / Alt+Right** bindings to decrease/increase the focused parameter value as an alternative to Q/W.
  - **Q** now decreases and **W** increases the focused parameter (was Q increase / A decrease). In legacy (unfocused) mode, Q/W adjusts octave down/up.
  - Added **,** (comma) and **.** (full\_stop) bindings for preset cycling;work in both focus and legacy modes.
  - All letter-key legacy shortcuts (E/D, R/F, T/G, Y/H, U/J, O/L, etc.) are silently suppressed while in focus mode to prevent accidental edits during navigation.

### Fixed
- **Synth Mode `IndexError: list index out of range`** (`modes/synth_mode.py`): When navigating left/right between sections, the param index was not clamped to the new section's param count. `_set_focus` now clamps on every section change.
- **Synth Mode Q/W (and Alt+←/→) had no effect in focus mode** (`modes/synth_mode.py`): The focus dispatch called the guarded `action_*` methods which immediately returned when focused. Extracted `_do_*` private helpers (no guard) for the actual engine mutations; `action_*` methods are now thin wrappers that guard then delegate; `_adjust_focused_param` calls `_do_*` directly.
- **Escape did not open quit dialog when unfocused** (`modes/synth_mode.py`): `action_nav_escape` was consuming the key event even when there was nothing to unfocus. Now calls `self.screen.action_quit_app()` when not focused.
- **`.` (full\_stop) preset-next binding had no effect** (`modes/synth_mode.py`): Textual 7.5 maps the `.` character to the key name `full_stop`, not `period`. Binding corrected.

## [1.4.1] - 2026-02-18

### Fixed
- **OS audio thread priority** (`music/synth_engine.py`): PortAudio callback thread now receives elevated OS scheduling priority at startup to prevent the Textual UI thread from starving it during widget rebuilds (mode switches).
  - **Windows**: `SetPriorityClass(ABOVE_NORMAL_PRIORITY_CLASS)` via `ctypes/kernel32`;no admin rights required.
  - **Linux**: `SCHED_FIFO` real-time scheduling via `pthread_setschedparam` + `PR_SET_TIMERSLACK` (100 µs) for tighter sleep granularity. Falls back to `os.nice(-10)` without `CAP_SYS_NICE`.
  - **macOS**: Mach `thread_policy_set(THREAD_TIME_CONSTRAINT_POLICY)`;the same API used by Core Audio. Falls back to `os.nice(-10)` on failure.
  - All paths are silent on failure;audio still works, just with less OS scheduling protection.
- **Thread-safe parameter routing** (`music/synth_engine.py`): `update_parameters()` and `all_notes_off()` now enqueue events rather than writing directly to shared attributes from the UI thread. Applied on the audio thread at the next buffer boundary, eliminating 25+ cross-thread data races that caused clicks when moving ADSR/filter knobs or switching modes while notes were playing.
- **Per-sample master gain ramp** (`music/synth_engine.py`): Voice count is now pre-calculated before the mixing loop so `gain_ramp` (via `np.linspace`) targets the correct value for the current buffer;previously lagged one buffer behind, producing a residual step discontinuity on voice-count changes.
- **Smooth silence gain decay** (`music/synth_engine.py`): `master_gain_current` now decays smoothly toward 1.0 during silence (coefficient 0.90/buffer) instead of hard-resetting, preventing a level spike on the first buffer after a silent gap. Smoothing coefficient tightened `0.98 → 0.80` so gain tracks voice-count changes within ~2 buffers (~10 ms).
- **Per-voice onset ramp** (`music/synth_engine.py`): 3 ms linear fade-in applied to each voice's post-envelope signal before the DC blocker on every new trigger. Suppresses the DC blocker's differentiator startup transient (first-sample high-frequency click) that was most audible on square and sawtooth waveforms at non-zero oscillator phases.
- **ANTI_I extended and repositioned** (`music/synth_engine.py`): Onset soft-start window extended from 2 ms to 5 ms to cover the DC blocker settling time. Moved to after the CROSS voice-steal crossfade so stolen voices still start from their pre-steal level;ANTI_I only attenuates, so both mechanisms compose cleanly.
- **Voice steal filter zero** (`music/synth_engine.py`): Filter and DC blocker states are explicitly zeroed before `trigger()` on a stolen voice, preventing stale frequency-domain state from the old note from bleeding into the new note's first few output samples.
- **Piano mode `on_mount`/`on_unmount`** (`modes/piano_mode.py`): Restored correct lifecycle structure;a linter had relocated `set_interval` and display initialisation into `on_unmount`, causing Piano Mode to show no display and produce no sound on first visit without a prior Synth Mode visit.
- **Stereo centre for single notes** (`music/synth_engine.py`): Pan table reordered so voice 0 (always the first triggered for any single note) is at `pan=0.5`;previously `0.35`, causing a ~63% L/R power imbalance on solo notes. Subsequent voices spread symmetrically outward in pairs.
- **tanh drive reduced** (`music/synth_engine.py`): `comp` multiplier lowered (`1.4 → 0.9` for sine) and post-tanh makeup gain added, keeping sustain-level signals in tanh's linear region. Eliminates the attack-peak/sustain-sag shape caused by differential saturation at different envelope stages.

## [1.3.0] - 2026-02-17

### Added
- **Polyphonic Synthesis Engine**:
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
- **8-Voice Polyphony**: Professional polyphonic synthesis with strict voice management.
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
- **Synth Preset System** (`music/preset_manager.py`;new module):
  - 10 factory presets covering a wide sonic range: `default`, `warm_pad`, `bright_saw_lead`, `deep_bass`, `soft_strings`, `church_organ`, `glass_bells`, `hollow_reed`, `plucky_square`, `vintage_synth`.
  - Presets stored as individual JSON files in `presets/`;easy to share, back up, or hand-edit.
  - Two-tier ordering: factory presets sorted alphabetically, user presets appended in creation order (newest always at end).
  - Save a new preset at any time with **Ctrl+N**;gets a randomly generated bilingual (English + European Portuguese) musical name (e.g. *amber reed*, *escuro sino*, *vazio echo*).
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
  - Fix: added change-detection guard (`_last_displayed_notes`);display updates only when the active note set actually changes.
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
