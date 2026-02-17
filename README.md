<img width="698" height="485" alt="image" src="https://github.com/user-attachments/assets/52cd7352-ebd7-45ea-8079-8854dd3f7cd8" />

# Acordes - MIDI Piano TUI Application

**Version 1.2.0**

A terminal-based MIDI piano application with real-time visualization, chord detection, traditional musical staff notation, a polyphonic synthesizer with a full preset system, and a fully-featured metronome.

## Features

- **Config Mode**: Display and select MIDI devices connected to your system.
- **Piano Mode**: Real-time visual piano keyboard showing notes and chord detection.
- **Synth Mode**: A 4-voice polyphonic synthesizer with real-time MIDI playback.
  - **Preset System** *(NEW in v1.2.0)*: 10 factory presets + unlimited user-saveable presets stored as individual JSON files.
  - **State Persistence** *(NEW in v1.2.0)*: Synth parameters survive mode switches and app restarts.
  - **Randomizer** *(NEW in v1.2.0)*: Generate musically useful random patches with a single key press.
- **Chord Compendium**: Reference guide with all chord types across all musical keys.
  - **Audio Playback**: Hear chords played as you browse.
- **Metronome Mode**: A highly customizable and musically aware metronome.
  - **Visual Beat Bar**: A large, centered bar visually displays the current beat in the measure.
  - **Selectable Time Signatures**: Cycle through common simple and compound time signatures (e.g., 2/4, 3/4, 4/4, 6/8, 9/8).
  - **Musically Correct Accents**: Automatically plays a stronger accent on the correct beats for each time signature (e.g., on beats 1 and 4 in 6/8).
  - **Italian Tempo Markings**: Displays the traditional name for the current tempo (e.g., *Andante*, *Allegro*).
  - **Adjustable BPM**: Wide tempo range from 50 to 300 BPM.

## What's New in v1.2.0

- **Synth Preset System**:
  - 10 factory presets covering a wide range of sounds (warm pad, bright saw, deep bass, glass bells, church organ, and more).
  - Save unlimited user presets with randomly generated bilingual (English + European Portuguese) musical names (e.g., *amber reed*, *escuro sino*, *vazio echo*).
  - Presets stored as individual JSON files in `presets/` — easy to share and back up.
  - Cycle through presets with **,** (previous) and **.** (next).
  - **Ctrl+N**: Save current parameters as a new preset.
  - **Ctrl+S**: Overwrite / update the currently loaded preset.
  - Preset bar always shows `[index/total] Preset Name` with a `*` dirty marker after any parameter change.
- **State Persistence**:
  - All synth parameters are autosaved to `config.json` on every change.
  - The last active preset is remembered and restored on the next app launch.
  - Switching to another mode and back restores parameters exactly as left.
- **Randomizer (`-` key)**:
  - Generates a complete random patch using musically weighted distributions.
  - Cutoff, attack, decay, and release use log-uniform scaling for natural timbral variety.
  - Resonance and sustain weighted towards the most useful ranges.
- **Piano Mode Performance Fix**:
  - Eliminated audio glitches when MIDI keys are held by removing unconditional 100Hz UI redraws.
  - Display now updates only when the active note set actually changes.
- **Synth Engine Sharing Fix**:
  - Resolved a bug where `SynthMode` was instantiating its own private `SynthEngine` instead of sharing the app-wide instance used by `PianoMode` and `CompendiumMode`.

## Requirements

- Python 3.8+
- MIDI input device (MIDI keyboard, controller, or virtual MIDI device)
- PyAudio & Pygame (for Synth and Metronome audio playback)

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
- 4-voice polyphonic synthesizer with real-time MIDI playback
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
│   ├── synth_engine.py          # 4-voice polyphonic audio synthesis engine
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
