# Acordes v1.11.0 - Analog Capacitor Simulation: Polyphonic MIDI Synthesizer & Piano TUI

## Application Overview

| | |
|:---:|:---:|
| ![Main Menu](docs/images/main-menu.png) | ![Piano Mode](docs/images/piano-mode.png) |
| ![Synth Mode](docs/images/synth-mode.png) | ![Tambor Mode](docs/images/tambor-mode.png) |

---

## About This Project

**Acordes** is a professional-grade, terminal-based MIDI synthesizer and piano application built with Python. It combines real-time MIDI input processing with a full 8-voice polyphonic synthesizer, musical reference tools, and a 16-step drum machine sequencer.

Whether you're a musician exploring synthesis in the terminal, a developer interested in audio DSP, or someone seeking a lightweight alternative to heavyweight DAWs, Acordes offers:

- **Real-time MIDI Playback**: Connect any USB MIDI keyboard and play instantly
- **Professional Polyphonic Synthesis**: 8-voice synthesis engine with dual-rank architecture, dual filters per voice, and a complete signal chain (VCO → HPF → LPF → Sine Reinforcement → Envelopes → FX)
- **Preset System**: 128 professionally programmed factory presets + unlimited user-saveable presets
- **Effects Processing**: BBD-style chorus, stereo feedback delay, and parametric filtering
- **Arpeggiator**: Sample-accurate, audio-thread driven arpeggiator (UP / DOWN / UP+DOWN / RANDOM)
- **Percussion Synthesis**: Dedicated drum machine mode with 16-step sequencer and 8 drum sounds
- **Musical Reference Tools**: Complete chord compendium, real-time chord detection, traditional music notation (bass & treble clefs)
- **Metronome**: Musically aware metronome with correct accentuation for time signatures
- **Velocity Curves**: Adaptive velocity response (Linear, Soft, Normal, Strong, Very Strong)

**Latest Version**: 1.11.0 - Analogue (Analog Capacitor Simulation)

---

## Features

### Config Mode
- Display and select MIDI input devices
- Select audio backend / host API (WASAPI, DirectSound on Windows; ASIO if provided; Core Audio on macOS; ALSA/PulseAudio on Linux)
- Display and select audio output devices (filtered by selected backend)
- Configure velocity curve response (5 types: Linear, Soft, Normal, Strong, Very Strong)
- 2×2 grid layout: Backend (top-left) | Audio Output (top-right) | MIDI Input (bottom-left) | Velocity (bottom-right)
- TAB to cycle between sections; ↑↓ to navigate within; SPACE to select

### Piano Mode
- Real-time visual 3-octave piano keyboard
- Live note highlighting
- Automatic chord detection and smart recognition
- Chord display above the keyboard
- Musical staff notation (side-by-side bass and treble clefs)

### Synth Mode: The Heart of Acordes
A full 8-voice polyphonic synthesizer with real-time MIDI playback:

**Synthesis Architecture**:
- **Dual Rank per Voice**: Two independent synthesis paths per note (Rank I & II)
- **Oscillators**: Sine, Square, Sawtooth, Triangle waveforms with PolyBLEP anti-aliasing and 4× internal oversampling
- **Dual-Filter Architecture**: MS-20 inspired HPF → LPF series (per rank) with selectable filter routing, soft saturation, per-stage resonance
- **Sine Reinforcement**: Post-filter sine wave for low-end solidity
- **Global LFO**: Modulates VCO (pitch), VCF (filter), and VCA (amplitude)

**Synthesis Parameters** (8 sections):
- **Oscillator**: Waveform, Octave (-2 to +2), Noise Level
- **Filter**: HPF/LPF Cutoff & Resonance, Filter Drive (0.5–8.0× pre-filter gain), Filter Routing (HP+LP / BP+LP / NT+LP / LP+LP), Key Tracking
- **Filter EG**: Independent envelope for filter modulation
- **Amp EG**: Amplitude envelope (ADSR)
- **LFO**: Shape (SIN/TRI/SQR/S&H), Rate, Depth, Target routing
- **Chorus**: BBD-style tape emulation, 1–4 voices, rate/depth/mix
- **FX**: Stereo delay (50 ms–2 s), feedback, wet/dry mix
- **Arpeggio**: UP / DOWN / UP+DOWN / RANDOM modes, BPM sync, gate length, octave range

**Effects & Processing**:
- **Chorus**: Tape-emulation with modulated multi-tap ring buffer
- **Delay**: Stereo ping-pong feedback delay with per-sample processing
- **Soft Clipping**: Smooth tanh saturation
- **DC Blocking**: Removes DC offset clicks
- **Crossfade**: 8-sample inter-buffer blending for click-free note transitions

**Audio Engine Quality**:
- **48 kHz sample rate** (professional audio standard)
- **Full vectorization**: NumPy/SciPy for ultra-low CPU usage
- **Click-free polyphony**: Smooth voice allocation, intelligent voice stealing
- **OS-level audio thread priority**: Elevated scheduling on Windows/Linux/macOS
- **Thread-safe parameter routing**: All changes via MIDI event queue
- **Sample-accurate timing**: Audio callback processes all MIDI events at buffer boundaries

**Analog Capacitor Simulation** (v1.11.0 Analogue):
- **Varicap Filter Modulation**: Loud input signals subtly darken the filter cutoff (up to 10%), modeling non-linear capacitor behavior under high drive in real analog circuits
- **Sustain Leakage**: Very long held notes drift slightly downward over ~6.5 seconds, simulating dielectric loss in analog envelope generator hold capacitors
- **Capacitor Waveshaper**: Frequency-dependent oscillator rounding via a leaky integrator (7% blend); low notes charge fully (near-identity), high notes soften transient peaks
- **RC Gate Curve**: Onset ramp uses exponential RC charge curve instead of linear, giving attacks the characteristic "fast rise then gradual approach" of real capacitor-gated analog circuits
- All effects are subtle, automatic, and transparent — no user controls needed

**Preset System**:
- **Factory Presets**: 128 professionally programmed presets across 8 categories (Bass, Leads, Pads, Plucked, Seq, FX, Misc, Synth)
- **User Presets**: Unlimited custom presets saved as individual JSON files
- **Randomizer**: Generate musically useful random patches with the `-` key
- **Parameter Persistence**: All tweaks auto-saved to disk; last preset restored on restart

**MIDI CC Mapping**:
- **16 Assignable Knobs** (4 banks × 4 knobs) configurable via `midi/cc_mappings.json`
- **Bank 1 (Fixed)**: CC 74 (LPF Cutoff), CC 71 (LPF Resonance), CC 75 (Wave Blend), CC 7 (Master Volume)
- **Banks 2-4**: Modulation depth, envelope parameters, filter controls, LFO, effects, arpeggiator
- **CC 75 Smart Mode**: In focus mode, CC 75 controls the currently highlighted parameter (continuous, discrete list, or discrete range)
- **Logarithmic Scaling**: Frequency parameters (cutoff, HPF, LFO rate) use log scaling for intuitive control

### Compendium Mode
A comprehensive music theory reference hub:
- **Chord Browser**: All 12 keys, 15+ chord types each
- **Scales & Modes**: Major, minor, harmonic, melodic, 7 diatonic modes, 15 exotic scales
- **Instruments**: 28 instruments organized by family (strings, brass, woodwinds, percussion, keyboard, vocal)
- **Genres**: 22+ musical genres with era, origin, characteristics, and subgenres
- **Real-time Search**: Filter all 258+ items instantly as you type
- **Chord Playback**: Hear chords as you browse

### Metronome Mode
- Large, visual beat bar display
- Customizable time signatures (2/4, 3/4, 4/4, 6/8, etc.) with musically correct accentuation
- Shared BPM with Arpeggiator
- Italian tempo markings (Andante, Allegro, Presto, etc.)

### Tambor Mode: Drum Machine
- **16-Step Sequencer**: Pattern-based drum programming
- **8 Drum Sounds**: Kick, Snare, Hi-Hats (open/closed), Clap, Toms (high/mid/low), Cowbell
- **64 Pattern Slots**: Save and recall your drum patterns
- **16 Fill Patterns**: Built-in fills with dynamic expansion
- **Controls**: Mute/solo, humanization, timing modes (straight/swing/shuffle)
- **BPM Sync**: Synchronized with metronome and arpeggiator

---

## Requirements

- **Python 3.11 or 3.12** (python-rtmidi lacks pre-built wheels for 3.13+)
- **MIDI Input Device** (USB MIDI keyboard, controller, or virtual MIDI)
- **Audio Output** (system speakers or audio interface)

### Platform-Specific Audio Setup

**Windows / macOS**: No extra setup needed. sounddevice ships pre-built wheels.

**Linux**: Install the PortAudio runtime library (the `run.sh` launcher does this automatically):
```bash
# Fedora / RHEL:
sudo dnf install portaudio

# Ubuntu / Debian:
sudo apt install libportaudio2

# Arch Linux:
sudo pacman -S portaudio
```

---

## Installation

### Prerequisites

**Install `uv`** (once, works across all platforms):

`uv` is a fast Python package and version manager that replaces both `pip` and `python -m venv`. It automatically handles Python version installation, dependency resolution, and virtual environments.

**Windows (PowerShell or CMD):**
```powershell
powershell -ExecutionPolicy BypassUser -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Linux / macOS:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or use your package manager:
- **macOS**: `brew install uv`
- **Ubuntu**: `sudo apt install uv` (or curl method above)
- **Fedora**: `sudo dnf install uv` (or curl method above)

For more installation options, see: https://docs.astral.sh/uv/getting-started/installation/

### Automatic Setup (Recommended)

Once `uv` is installed, just run the launcher script:

**Windows (PowerShell):**
```powershell
.\run.ps1
```

**Linux / macOS:**
```bash
chmod +x run.sh   # only needed once after a fresh git clone
./run.sh
```

> **Fresh clone on Linux?** The script may not be executable after cloning. Run `chmod +x run.sh` once before the first launch.

The launcher automatically:
1. Installs `uv` if not found (via the official curl installer)
2. Installs system audio libraries (PortAudio headers) if missing; uses `dnf`, `apt`, `pacman`, or `brew`
3. Pins and installs Python 3.12 automatically if not present
4. Syncs all Python dependencies with `uv sync`
5. Launches the application

### Manual Setup (Advanced)

If you prefer explicit control:

```bash
# Pin Python version (automatic in launcher)
uv python pin 3.12

# Sync dependencies (creates .venv automatically)
uv sync

# Run the application
uv run python main.py

# Or activate the virtual environment manually
source .venv/bin/activate         # Linux/macOS
.venv\Scripts\activate            # Windows
python main.py
```

---

## Updating Acordes

To update to a new version:

### Option 1: Using Git (Recommended)

If you cloned the repository with `git clone`, pull the latest changes:

```bash
# Navigate to the Acordes directory
cd path/to/Acordes

# Check for updates
git status

# Pull the latest changes
git pull origin main

# Re-sync dependencies (uv will reinstall any new packages)
uv sync
```

Then run the app normally:

```bash
# Windows
.\run.ps1

# Linux / macOS
./run.sh
```

### Option 2: Manual Update (If Git is Not Available)

1. Download the latest source code from [GitHub](https://github.com/pushpop/Acordes)
2. Extract it to a new folder (or replace your existing folder)
3. Delete the `.venv/` folder (if it exists) to ensure a clean install
4. Run the launcher (`run.ps1` or `run.sh`) to reinstall dependencies and start the app

### Preserving Your Settings

Your configuration and user presets are stored in `config.json` and `presets/` and will **not** be overwritten by updates. They are safe to keep.

### Checking Your Version

In the app, look at the window title which displays the current version (e.g. `Acordes v1.10.1 - Grasp`).

---

## Quick Start

1. **Connect a MIDI Device**: Plug in a USB MIDI keyboard or controller
2. **Open the App**: Run `.\run.ps1` (Windows) or `./run.sh` (Linux/macOS)
3. **Select Your Device**: Press **C** → navigate → **Space** to select MIDI input
4. **Play Piano**: Press **1** → play notes on your MIDI keyboard
5. **Explore Synth**: Press **3** → play to hear the current preset
6. **Browse Presets**: Press **N** → scroll through 128 factory presets

For complete keyboard controls, see **[KEYBINDS.md](KEYBINDS.md)**.
For Xbox-style gamepad controller support, see **[GAMEPAD.md](GAMEPAD.md)**.

### What's New (v1.10.1 - Grasp)

**Output Gain Optimization & Bug Fixes**:
- **Key Tracking Parameter Fix**: Parameter updates were silently dropped due to missing `self.key_tracking` attribute in hasattr() check. Now fully responsive with smooth 90ms ramping (0-100% range affects filter brightness across the keyboard).
- **Output Makeup Gain**: Added +3 dB pre-saturation boost to compensate for unused headroom from conservative per-voice normalization. Single voices now output at -3.6 dBFS (vs. previous -8 dBFS) without changing saturation character or affecting high-drive presets.
- **Platform-Level Improvements**: Refined dithering integration and filter stability across desktop/ARM platforms.

**v1.10.0 - Full Xbox-Style Gamepad Controller Support**:
- **Platform Coverage**: Windows (XInput API), Linux x86_64/ARM (evdev), macOS (Pygame controller)
- **All Modes Playable**: Every mode (Main Menu, Piano, Synth, Compendium, Metronome, Tambor) fully navigable with controller
- **Smart Input Routing**:
  - Windows: Native XInput via ctypes (no SDL overhead, eliminates Windows Terminal keyboard injection crashes)
  - Linux/ARM: Evdev direct input (/dev/input/event*) with hot-plug support
  - macOS: SDL2 controller system
- **Combo System**: Global keyboard-style combos (START + BACK opens config, LB + RB panic, RB + A = preset browser)
- **Multi-Screen Guards**: Prevents accidentally stacking multiple config/dialog screens when button is held
- **Per-Mode Callbacks**: Each mode registers its own gamepad bindings on enter, clears on exit
- **Full Feature Parity**: All synth parameters adjustable via LT/RT trigger axes, all modes have complete controller navigation
- **Configuration**: Config mode has full gamepad support (DPAD navigate, A select, B close, LB/RB cycle sections)
- **Dynamic Combo Priority**: Most specific combo fires first (LB+RB+Start route priority over LB+RB panic)

See **[GAMEPAD.md](GAMEPAD.md)** for complete controller reference and keybindings.

### What's New (v1.9.4 - Amora)

**Raspberry Pi / ARM Support**:
- Runs on Raspberry Pi 4B (1GB RAM, armv7l) and compatible ARM SBCs
- Auto-detected ARM profile: 4 voices, 960-sample buffer (20ms), no oversampling, no PolyBLEP
- Chorus and delay DSP blocks force-bypassed on ARM to stay within CPU budget
- Patchbox-style system tweaks applied at launch: CPU governor set to `performance`, audio RT limits, VM swappiness reduced
- TFT framebuffer console font auto-set to Terminus Bold 14 for readability on small screens
- Responsive UI layout: main menu buttons and config panel scale to terminal width
- Python 3.11 selected automatically on ARM for piwheels compatibility
- Multiprocessing fd patch for Python 3.11 ARM bug (ValueError in resource tracker)
- run.sh auto-installs ARM build dependencies (gfortran, ninja, libffi-dev)

### What's New (v1.9.2)

**MIDI CC Mapping System**:
- Configure 16 assignable MIDI CC knobs (4 banks of 4 knobs) via `midi/cc_mappings.json`
- Bank 1 pre-configured: CC 74 (cutoff), CC 71 (resonance), CC 75 (wave blend), CC 7 (volume)
- Smart CC 75 in focus mode: Controls the focused parameter whether continuous or discrete
- Section-aware parameter lookup resolves naming conflicts (e.g., LFO Depth vs Chorus Depth)
- Logarithmic scaling for frequency parameters ensures intuitive sweeps

**Noise Engine Improvement**:
- Switched from white to pink noise (1/f spectrum, warmer and more musical)
- Noise now blended pre-filter so VCF shapes it alongside the tone (analog synth behavior)
- Square-root curve on noise blend level keeps values subtle and musical across the full range

**Filter Responsiveness Fix**:
- Engine-level resonance smoothing optimized: instant response with per-voice artifact protection
- HPF resonance now fast 3-buffer ramp (~32ms) for responsive control
- HPF Q range increased to match LP filter (0.5-10.0 scale) fixing weak HP peak in MS-20 routing

**Previous Version (v1.9.0)**:

**Audio Backend Selection**:
- Config mode now displays and selects audio backends / host APIs (WASAPI, DirectSound on Windows; ASIO via optional DLL; Core Audio on macOS; ALSA/PulseAudio on Linux)
- OS-aware backend recommendation on first launch (ASIO → WASAPI → DirectSound on Windows)
- Devices list filtered by selected backend for cleaner UI
- Backend selection persists across restarts in `config.json`

**ASIO Support on Windows**:
- ASIO-enabled PortAudio DLL downloaded automatically on first launch from spatialaudio/portaudio-binaries
- No manual steps: launcher handles download, caching, and installation into the venv
- Supports Steinberg ASIO, ASIO4ALL, and all installed ASIO drivers
- Graceful fallback to WASAPI if no internet on first launch

**Config Mode UI Redesign**:
- New 2×2 grid layout instead of vertical scroll
- Top row: Audio Backend | Audio Output Device
- Bottom row: MIDI Input Device | Velocity Curve
- Tab-navigable sections for faster configuration without scrolling

**Performance Optimizations**:
- Asymmetric gain smoothing: instant snap down when voices join, smooth ramp up on release (eliminates gain dip artifacts in poly mode)
- Reduced oversampling from 4× (192 kHz) to 2× (96 kHz) for CPU savings on high-voice counts
- Increased audio buffer from 528 to 1024 samples for better headroom on resource-constrained systems
- Removed per-stage saturator overhead in ladder filter for lower latency

**Previous Release (v1.8.11)**:
- Fixed critical race condition in chord browser causing noise/artifacts
- Configuration auto-save (System Default audio device, optional MIDI)
- Textual timer-based stagger effects with debounce

**Earlier (v1.8.9+)**:
- PyAudio → sounddevice migration
- Audio device selection at startup

See **[CHANGELOG.md](CHANGELOG.md)** for full technical details.

---

## Technical Architecture

### Key Components

```
┌─ Audio Engine (music/synth_engine.py)
│  ├─ 8-voice polyphonic synthesis (voices 0-7)
│  ├─ Dual-rank per-voice architecture
│  ├─ MIDI event queue (thread-safe parameter routing)
│  ├─ sounddevice real-time I/O (48 kHz, 1024-sample buffer)
│  └─ Preset manager with factory + user presets
│
├─ MIDI I/O (midi/)
│  ├─ Device manager (device detection, enumeration)
│  └─ Input handler (velocity curve remapping)
│
├─ UI Modes (modes/)
│  ├─ Config Mode (MIDI device + velocity curve)
│  ├─ Piano Mode (visualization + chord detection)
│  ├─ Synth Mode (parameter editing + preset browsing)
│  ├─ Compendium Mode (music theory reference)
│  ├─ Metronome Mode (BPM control, accentuation)
│  └─ Tambor Mode (16-step drum sequencer)
│
└─ Music Theory (music/)
   ├─ Chord detector
   ├─ Chord library (1000+ chords)
   ├─ Velocity curves (5 response types)
   └─ Factory preset definitions (128 presets)
```

### Audio Signal Flow (Per Voice)

```
MIDI Input
  ↓
Velocity Curve Remapping (config_manager)
  ↓
SynthEngine.note_on() / note_off()
  ↓
Voice Allocation (8-voice polyphony with stealing)
  ↓
[Per Voice]
  Oscillator (VCO) → HPF → LFO (modulation) → LPF → Sine Reinf. → Envelopes → Pan → Mix
  ↓
[Global]
  Master Gain (per-voice polyphony compensation) → Chorus → Delay → Soft Clipping (tanh) → DC Blocker → Output

Audio Callback (48 kHz)
  ↓
sounddevice (PortAudio) → System Audio Output
```

### Key Design Decisions

1. **Thread Safety**: MIDI → audio thread communication exclusively via event queue, eliminating data races
2. **Click-Free Design**: Voice allocation with crossfade, per-voice onset ramp, inter-buffer sample continuity
3. **Low CPU Usage**: Full NumPy/SciPy vectorization eliminates Python loops in real-time callback
4. **Parameter Persistence**: Separate config file + synth state auto-save on every change
5. **Modular Modes**: Each mode is independently mounted/unmounted; shared synth engine passed via app context

---

## Troubleshooting

### Python Version (3.13+ Not Supported)

python-rtmidi lacks pre-built wheels for Python 3.13+. Use Python 3.12:

```
https://www.python.org/downloads/python-3.12.10/
```

You can have multiple Python versions installed side-by-side. After installing 3.12, delete `.venv/` and run the launcher again.

### No Sound (Synth / Metronome Mode)

1. **Linux**: Install the PortAudio runtime library (the `run.sh` script does this automatically):
   ```bash
   # Fedora / RHEL:
   sudo dnf install portaudio

   # Ubuntu / Debian:
   sudo apt install libportaudio2

   # Arch Linux:
   sudo pacman -S portaudio
   ```
   Then run `./run.sh` again.

2. **macOS**: Install via Homebrew:
   ```bash
   brew install portaudio
   ```

3. **Windows**: sounddevice ships pre-built wheels — no extra steps required.
   If you encounter issues, ensure your audio drivers are up to date.

### ASIO Support on Windows

By default, sounddevice on Windows uses WASAPI or DirectSound. ASIO support (for lower latency and better hardware compatibility) is enabled **automatically** on first launch:

1. Run `.\run.ps1` as normal
2. The launcher downloads the ASIO-enabled PortAudio DLL from [spatialaudio/portaudio-binaries](https://github.com/spatialaudio/portaudio-binaries) and installs it automatically (one-time download, cached locally)
3. In the app, press **C** for config. "ASIO" will appear in the Audio Backend list alongside WASAPI and DirectSound. Select it, then pick your ASIO device.

No manual steps required. If there is no internet connection on first launch, the launcher skips the download silently and the app runs with WASAPI as the default backend. ASIO will be set up automatically on the next launch when internet is available.

The original sounddevice DLL is backed up as `libportaudio64bit.dll.bak` so you can restore the default if needed.

#### Important: ASIO is Exclusive (by Design)

ASIO drivers take **exclusive control** of the audio hardware. When Acordes holds an ASIO stream open, other applications (Firefox, Spotify, Discord, etc.) cannot play audio simultaneously. This exclusivity is why ASIO has low latency — it bypasses the Windows audio mixer entirely.

**Solutions**:

1. **Switch backends dynamically**: Use WASAPI when you need to multitask (press **C** in config, select WASAPI). Use ASIO only when doing focused music work.

2. **Use FlexASIO** (Recommended for shared audio): [FlexASIO](https://github.com/dechamps/FlexASIO) is a free virtual ASIO driver that wraps WASAPI shared mode underneath. It provides ASIO-style low latency while allowing other apps to use audio simultaneously.
   - Download and install from: [github.com/dechamps/FlexASIO](https://github.com/dechamps/FlexASIO)
   - After installation, "FlexASIO" will appear in Acordes' ASIO driver list
   - When you select FlexASIO in config, Acordes automatically generates an optimized `FlexASIO.toml` file with settings matched to the Acordes engine:
     - 1024-sample buffer (≈21ms latency @ 48 kHz)
     - Float32 sample type
     - Minimal suggested latency (0.0 seconds)
     - WASAPI exclusive mode for lowest CPU overhead
   - The config file is created at: `C:\Users\<username>\AppData\Local\FlexASIO.toml`
   - FlexASIO reads the config on next restart — no manual configuration needed

3. **ASIO Driver Options**: Acordes supports all ASIO drivers installed on your system:
   - **Steinberg ASIO** (native hardware ASIO from Steinberg; requires hardware support): Lowest latency, exclusive access
   - **ASIO4ALL** (free wrapper for WDM drivers): Wraps Windows audio drivers as ASIO, still exclusive like standard ASIO
   - **FlexASIO** (free virtual ASIO over WASAPI shared): Allows simultaneous audio from other apps

**FlexASIO Lag Fix**: If FlexASIO feels laggy before auto-configuration kicks in, the issue is likely a buffer size mismatch. Acordes runs at 48 kHz with a 1024-sample buffer. The auto-generated config ensures FlexASIO matches these settings. For advanced tuning, see [FlexASIO Configuration](https://github.com/dechamps/FlexASIO/blob/master/CONFIGURATION.md).

### No MIDI Devices Found

1. Ensure your MIDI device is connected
2. On Linux, install ALSA MIDI support:
   ```bash
   sudo apt-get install libasound2-dev
   ```
3. On macOS, CoreMIDI should work out of the box
4. On Windows, ensure MIDI device drivers are installed

### Permission Issues (Linux)

Add your user to the audio group:
```bash
sudo usermod -a -G audio $USER
```

Then log out and log back in.

---

## Project Structure

```
acordes/
├── main.py                          # Application entry point
├── config_manager.py                # Config persistence (devices, presets, synth state)
├── CLAUDE.md                        # Project instructions & architecture guide
├── KEYBINDS.md                      # Comprehensive keyboard shortcut reference
├── CHANGELOG.md                     # Version history and release notes
│
├── components/                      # UI widgets
│   ├── piano_widget.py
│   ├── chord_display.py
│   ├── staff_widget.py
│   ├── header_widget.py
│   └── confirmation_dialog.py
│
├── gamepad/                         # Xbox-style gamepad controller support
│   ├── input_handler.py             # Main gamepad polling & callback system
│   ├── xinput_backend.py            # Windows XInput API (pure ctypes)
│   ├── pygame_backend.py            # macOS/Linux x86 Pygame controller
│   ├── evdev_backend.py             # Linux ARM evdev direct input
│   ├── actions.py                   # Gamepad action constants (GP class)
│   └── button_maps.py               # Button to action mappings per backend
│
├── modes/                           # Screen modes (all inherit from Textual Widget)
│   ├── config_mode.py               # MIDI device + velocity curve selection
│   ├── piano_mode.py                # Real-time piano visualization + chord detection
│   ├── compendium_mode.py           # Music theory reference hub
│   ├── synth_mode.py                # Synthesizer parameter editing + preset browser
│   ├── metronome_mode.py            # Customizable metronome with time signatures
│   └── tambor/                      # Drum machine mode
│       ├── tambor_mode.py           # Main drum sequencer UI
│       ├── music/
│       │   ├── pattern_manager.py   # Pattern persistence
│       │   └── drum_voice_manager.py
│       └── ui/
│           ├── drum_editor.py
│           └── fill_selector.py
│
├── midi/                            # MIDI I/O
│   ├── device_manager.py            # Device enumeration & selection
│   ├── input_handler.py             # MIDI input processing + velocity curve remapping
│   └── cc_mappings.json             # MIDI CC to parameter mapping (16 assignable knobs)
│
├── music/                           # Audio synthesis & music theory
│   ├── synth_engine.py              # 8-voice polyphonic synthesizer (core audio)
│   ├── preset_manager.py            # Preset load/save/cycle
│   ├── factory_presets.py           # 128 factory presets (8 categories)
│   ├── velocity_curves.py           # Velocity remapping curves
│   ├── chord_detector.py            # Real-time chord recognition
│   └── chord_library.py             # Chord database (1000+ chords)
│
├── presets/                         # Synth preset JSON files
│   ├── default.json
│   ├── warm_pad.json
│   └── ...                          # User presets saved here
│
├── docs/                            # Documentation
│   └── images/                      # Screenshots
│       ├── main-menu.png
│       ├── piano-mode.png
│       ├── synth-mode.png
│       └── tambor-mode.png
│
├── run.ps1                          # Windows (PowerShell) launcher
├── run.sh                           # Linux/macOS launcher
├── requirements.txt                 # Python dependencies
└── LICENSE                          # GPL-3.0-or-later
```

---

## Technology Stack

- **TUI Framework**: [Textual](https://textual.textualize.io/) (modern Python TUI library)
- **MIDI I/O**: [mido](https://mido.readthedocs.io/) + [python-rtmidi](https://github.com/SpotlightKid/python-rtmidi)
- **Audio**: [sounddevice](https://python-sounddevice.readthedocs.io/) (PortAudio bindings), [Pygame](https://www.pygame.org/)
- **DSP**: [NumPy](https://numpy.org/), [SciPy](https://scipy.org/) (vectorized signal processing)
- **Music Theory**: [mingus](https://github.com/bartmejias/mingus) (chord recognition)

---

## Contributing & Customization

Acordes is designed for musicians and developers who want to:
- Understand synthesizer architecture at a code level
- Customize the sound palette with new factory presets
- Extend the UI with new modes
- Experiment with different DSP algorithms

All core synthesis happens in `music/synth_engine.py`. The parameter system is flexible and open to modification.

---

## License

GNU General Public License v3 or later (GPL-3.0-or-later); see [LICENSE](LICENSE) for details.

---

## Version & History

For complete version history, release notes, and technical details about each update, see **[CHANGELOG.md](CHANGELOG.md)**.

---

*For detailed keyboard shortcuts and navigation, see **[KEYBINDS.md](KEYBINDS.md)**.*

*For Xbox-style gamepad controller support and full button reference, see **[GAMEPAD.md](GAMEPAD.md)**.*
