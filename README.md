<img width="698" height="485" alt="image" src="https://github.com/user-attachments/assets/52cd7352-ebd7-45ea-8079-8854dd3f7cd8" />

# Acordes - MIDI Piano TUI Application

**Version 1.4.0**

A terminal-based MIDI piano application with real-time visualization, chord detection, traditional musical staff notation, a polyphonic synthesizer with a full preset system, and a fully-featured metronome.

## Features

- **Config Mode**: Display and select MIDI devices connected to your system.
- **Piano Mode**: Real-time visual piano keyboard showing notes and chord detection.
- **Synth Mode**: An 8-voice polyphonic synthesizer with real-time MIDI playback.
  - **CS-80 Emulation** *(v1.3.0)*: Precision emulation of the Yamaha CS-80 architecture.
    - **Dual Rank Architecture**: Two independent synthesis paths per note.
    - **Series Filtering**: High-Pass Filter (HPF) into Low-Pass Filter (LPF) per rank.
    - **Sine Reinforcement**: Post-filter pure sine wave for solid low-end.
    - **Global Sub-Oscillator (LFO)**: Modulates VCO (Pitch), VCF (Filter), and VCA (Volume) across all voices.
  - **Performance Optimizations** *(v1.3.0)*: Full NumPy and SciPy vectorization for ultra-low CPU usage.
  - **MIDI Expressivity** *(v1.3.0)*: Support for MIDI Note-Off (Release) Velocity.
  - **Master Section** *(v1.3.0)*: Post-saturation Master Volume control with smooth gain protection.
  - **DSP Correctness & Click-Free Polyphony** *(NEW in v1.4.0)*: Full audio engine audit and fix — filter stability, sine waveform accuracy, phase continuity, gain staging, and polyphonic click elimination.
  - **Preset System**: 10 factory presets + unlimited user-saveable presets stored as individual JSON files.
  - **Randomizer**: Generate musically useful random patches with a single key press.
- **Chord Compendium**: Reference guide with all chord types across all musical keys.
  - **Audio Playback**: Hear chords played as you browse.
- **Metronome Mode**: A highly customizable and musically aware metronome.

## What's New in v1.4.0

A focused DSP quality release — no new features, only fixes to audio engine correctness, polyphonic click elimination, and UI accuracy.

### Audio Engine Correctness
- **IIR Filter rebuilt**: Resonance feedback was warping the pole coefficient, causing instability at high resonance. Now uses the correct 1-pole topology — stable and musical at all settings.
- **Sine waveform fixed**: The "warm sine" Taylor approximation was operating at `±π` (outside its convergence radius), producing heavy distortion. Replaced with `sin()` + 1% 2nd harmonic blend.
- **Filter keyboard tracking corrected**: The octave transpose was being applied twice in filter tracking. Fixed to use the pre-octave base frequency.
- **HPF/LPF cancellation guard**: Under certain velocity + tracking conditions the HPF could exceed the LPF, silencing the voice. HPF is now always capped at least one octave below the LPF.
- **Sub-oscillator phase continuity**: The sine-reinforcement oscillator was restarting from a stale phase every buffer, producing a periodic click. Now uses a dedicated per-voice phase accumulator.
- **Release time corrected**: A `/4` divisor in the release time constant was making release 4× shorter than the UI value. Removed — the slider now means what it says.
- **Gain staging corrected**: Master Volume is now applied before `tanh()` soft-clipping so it controls drive into the clipper, not just output level.

### Click-Free Polyphony
- **Polyphony gain ramp**: The per-voice gain compensation (`1/√N`) previously jumped in a single buffer when voices were added or removed, causing an audible click. Now ramps smoothly over ~25 ms.
- **Voice steal crossfade**: Extended from 3 ms (exponential) to 8 ms (linear) — stolen voices dissolve into new attacks without a pop.
- **Sine wrap-point tick**: The old 2% sawtooth blend in "warm sine" caused a discontinuity at each phase-rollover, audible as a periodic tick on low notes. Replaced with a 2nd-harmonic sine blend.
- **DC blocker reset on steal**: Filter and DC-blocker state from a stolen voice no longer bleeds into the new note's onset.

### Stereo Image
- **Symmetric pan spread**: All 8 voices now spread symmetrically around centre in equal steps (±15%, ±10%, ±6%, ±2%) — previously only voices 0–1 had meaningful stereo width.

### UI Fixes
- MIXER section Amp label corrected from `"Preset [up/down]"` to `"Amp [↑/↓]"`.
- Envelope time display now shows milliseconds for all values below 1 s (was switching at 10 ms).

---

## What's New in v1.3.0

- **CS-80 Architecture**:
  - Implemented the legendary Dual Rank system where each key triggers two independent synth engines.
  - Added Series HPF -> LPF filtering for precise timbral windowing.
  - Added Sine Reinforcement to maintain bass "heft" during aggressive filtering.
  - Global Sub-Oscillator (LFO) for hardware-authentic modulation.
- **Pro Audio Improvements**:
  - **8-Voice Polyphony**: Strictly limited to 8 voices to match the original CS-80 hardware.
  - **Vectorized DSP**: All oscillators, filters, and envelopes refactored with NumPy/SciPy for high performance.
  - **Click-Free Performance**: Implemented free-running oscillators and smoothed gain transitions.
  - **DC Blocker Refinement**: Eliminated "DC Crush" artifacts for rock-solid tonal stability.
- **Master Section**:
  - New Master Volume control (post-saturation) using **[** and **]** keys.
  - Redesigned MIXER UI section showing both Preset and Master levels.
- **MIDI Expressivity**:
  - Full support for MIDI Release Velocity, allowing key release speed to modulate the sound.

## Requirements

- Python 3.8+
- MIDI input device (MIDI keyboard, controller, or virtual MIDI device)
- PyAudio, SciPy & NumPy (for high-performance Synth playback)
- Pygame (for Metronome audio playback)

## Installation

1. Create a virtual environment and install dependencies:

**Windows:**
```cmd
python -m venv venv
venv\Scripts\pip.exe install -r requirements.txt
```

**Linux/macOS:**
```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Usage

Run the application using the virtual environment:

### Windows

**Option 1: Using the convenience script (Command Prompt)**
```cmd
run.bat
```

**Option 1b: Using PowerShell**
```powershell
.\run.ps1
```

**Option 2: Direct invocation (adjust path based on your venv)**
```cmd
REM Native Windows venv
venv\Scripts\python.exe main.py

REM Git Bash/WSL-style venv
venv\bin\python.exe main.py
```

**Option 3: Activate virtual environment first**
```cmd
REM Command Prompt (native Windows venv)
venv\Scripts\activate
python main.py

REM PowerShell (native Windows venv)
venv\Scripts\Activate.ps1
python main.py

REM Git Bash (Unix-style venv)
source venv/bin/activate
python main.py
```

### Linux/macOS

**Option 1: Using the convenience script**
```bash
./run.sh
```

**Option 2: Direct invocation**
```bash
./venv/bin/python main.py
```

**Option 3: Activate virtual environment first**
```bash
source venv/bin/activate
python main.py
```

### Keyboard Controls

#### Global Controls
- **1**: Switch to Piano Mode
- **2**: Switch to Compendium Mode
- **3**: Switch to Synth Mode
- **4**: Switch to Metronome Mode
- **C**: Open Config Mode
- **Escape**: Quit application (with confirmation dialog)

#### Mode-Specific Controls
- **Arrow Keys**: Navigate within Config and Compendium modes
- **Enter**: Select/Expand items
- **Space**: Refresh device list (Config Mode only)

#### Synth Mode Controls

**Presets:**
- **,** / **.**: Previous / Next preset
- **Ctrl+N**: Save current parameters as a new preset
- **Ctrl+S**: Overwrite / update the current preset
- **-**: Randomize all parameters (musically weighted)

**Parameters:**
- **W**: Toggle waveform (Sine → Square → Sawtooth → Triangle)
- **S / X**: Octave transpose up / down (−2 to +2)
- **↑ / ↓**: Adjust master volume
- **← / →**: Adjust filter cutoff frequency
- **Q / A**: Increase / Decrease resonance
- **E / D**: Increase / Decrease attack time
- **R / F**: Increase / Decrease decay time
- **T / G**: Increase / Decrease sustain level
- **Y / H**: Increase / Decrease release time
- **U / J**: Increase / Decrease intensity
- **Space**: Panic — silence all voices immediately

#### Metronome Mode Controls
- **P / Space**: Start or stop the metronome.
- **↑ / ↓**: Increase or decrease the tempo (BPM).
- **← / →**: Cycle through different time signatures.

### Modes

#### Config Mode
- View all available MIDI input devices
- Select a device to use for Piano Mode
- Press Space to refresh the device list

#### Piano Mode
- Visual 3-octave piano keyboard display
- Real-time note highlighting in red
- Automatic chord detection with smart recognition
- Chord names displayed centrally above the keyboard
- Side-by-side musical staff notation:
  - **Bass Clef (F)**: Displays notes below B3 (MIDI 59)
  - **Treble Clef (G)**: Displays notes B3 and above
  - Notes appear as yellow dots (●) on the staff lines
  - Sharp notes marked with ♯ symbol
  - Reference note labels on the right side of each staff

#### Compendium Mode
- Browse complete chord library
- All 12 keys (C through B)
- 15+ chord types per key
- View chord notes for reference

#### Synth Mode
- 8-voice polyphonic synthesizer with real-time MIDI playback
- **Preset System**: 10 factory presets + unlimited user presets saved in `presets/`
  - Cycle presets with `,` / `.`, save with **Ctrl+N**, update with **Ctrl+S**
  - Presets remembered across mode switches and app restarts
- **Randomizer**: Press `-` to instantly generate a new random patch
- **Oscillator**: Sine, Square, Sawtooth, and Triangle waveforms with octave transpose
- **Filter**: Low-pass filter with logarithmic cutoff (20Hz–20kHz) and resonance
- **Envelope**: Full ADSR (Attack, Decay, Sustain, Release) + Intensity
- **AMP**: Master volume with automatic waveform gain compensation
- **MIDI Controllers**: Pitch bend (±2 semitones) and modulation wheel (CC1)

#### Metronome Mode *(NEW in v1.1.0)*
- A large, centered visual "beat bar" shows the current beat in the measure.
- Cycle through common time signatures like 2/4, 3/4, 4/4, 6/8, and more.
- The metronome automatically applies the correct strong and weak accent patterns for each signature.
- The traditional Italian tempo name for the current BPM is always visible.

## Project Structure

```
acordes/
├── main.py                      # Application entry point
├── config_manager.py            # Configuration persistence (MIDI device, synth state, last preset)
├── components/                  # UI widgets
│   ├── piano_widget.py          # Visual piano keyboard
│   ├── chord_display.py         # Chord name display
│   ├── staff_widget.py          # Musical staff notation display
│   ├── header_widget.py         # Unified header/title widget
│   └── confirmation_dialog.py   # Quit confirmation
├── modes/                       # Screen modes
│   ├── config_mode.py           # MIDI device configuration
│   ├── piano_mode.py            # Real-time piano display
│   ├── compendium_mode.py       # Chord reference
│   ├── synth_mode.py            # Synthesizer interface with preset system
│   ├── metronome_mode.py        # Metronome interface
│   └── main_menu_mode.py        # Main menu
├── midi/                        # MIDI handling
│   ├── device_manager.py        # Device detection
│   └── input_handler.py         # MIDI input processing
├── music/                       # Music theory and synthesis
│   ├── chord_detector.py        # Chord recognition (supports 9th, 11th, 13th chords)
│   ├── chord_library.py         # Chord database
│   ├── synth_engine.py          # 8-voice polyphonic audio synthesis engine
│   └── preset_manager.py        # Synth preset load/save/cycle (NEW in v1.2.0)
├── presets/                     # Synth preset JSON files (NEW in v1.2.0)
│   ├── default.json             # Factory presets (10 total)
│   ├── warm_pad.json
│   ├── bright_saw_lead.json
│   └── ...                      # User presets saved here automatically
├── run.bat                      # Windows launcher (Command Prompt)
├── run.ps1                      # Windows launcher (PowerShell)
├── run.sh                       # Linux/macOS launcher
├── scripts/                     # Installation and setup scripts
└── docs/                        # Documentation and development notes
```

## Technology Stack

- **Textual**: Modern TUI framework
- **mido**: MIDI I/O library
- **python-rtmidi**: Real-time MIDI backend
- **mingus**: Music theory library
- **PyAudio**: Real-time audio I/O
- **Pygame**: Audio mixer for metronome sounds
- **NumPy**: Numerical computing for audio synthesis

## Troubleshooting

### Audio Not Available (Synth / Metronome Mode)

If you have audio issues:

1. Install PyAudio & Pygame:
   ```bash
   pip install pyaudio pygame
   ```

2. On Windows, you may need to install it via pre-built wheels:
   ```bash
   pip install pipwin
   pipwin install pyaudio
   pipwin install pygame
   ```

3. On Linux:
   ```bash
   sudo apt-get install portaudio19-dev python3-pyaudio python3-pygame
   pip install pyaudio pygame
   ```

4. On macOS:
   ```bash
   brew install portaudio sdl2 sdl2_mixer
   pip install pyaudio pygame
   ```

### No MIDI Devices Found

1. Ensure your MIDI device is connected
2. On Linux, you may need to install ALSA MIDI support:
   ```bash
   sudo apt-get install libasound2-dev
   ```
3. On macOS, CoreMIDI should work out of the box
4. On Windows, ensure your MIDI device drivers are installed

### Permission Issues (Linux)

Add your user to the audio group:
```bash
sudo usermod -a -G audio $USER
```

Then log out and log back in.

## License

MIT License
