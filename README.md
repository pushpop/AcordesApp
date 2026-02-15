<img width="698" height="485" alt="image" src="https://github.com/user-attachments/assets/52cd7352-ebd7-45ea-8079-8854dd3f7cd8" />

# Acordes - MIDI Piano TUI Application

**Version 1.0.1**

A terminal-based MIDI piano application with real-time visualization, chord detection, traditional musical staff notation, and a monophonic synthesizer.

## Features

- **Config Mode**: Display and select MIDI devices connected to your system
- **Piano Mode**: Real-time visual piano keyboard showing notes and chord detection
  - 3-octave visual keyboard display with color-coded keys
  - Real-time chord name display positioned above the keyboard
  - **Musical Staff Display**: Side-by-side Bass Clef (F) and Treble Clef (G) notation
  - Notes appear as yellow dots (●) on the staff as you play
  - Sharp notes (♯) are clearly marked
  - Automatic note distribution across both clefs based on pitch
- **Synth Mode** *(NEW in v1.0.1)*: Monophonic synthesizer with real-time MIDI playback
  - Three waveforms: Sine, Square, Triangle
  - Mixer with volume control
  - Low-pass filter with adjustable cutoff and resonance
  - Envelope generator with Attack, Decay, and Intensity controls
  - Interactive keyboard controls for all parameters
  - Real-time audio synthesis using PyAudio
- **Chord Compendium**: Reference guide with all chord types across all musical keys

## Requirements

- Python 3.8+
- MIDI input device (MIDI keyboard, controller, or virtual MIDI device)
- PyAudio (optional, required for Synth Mode audio playback)

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
- **C**: Open Config Mode
- **Escape**: Quit application (with confirmation dialog)

#### Mode-Specific Controls
- **Arrow Keys**: Navigate within Config and Compendium modes
- **Enter**: Select/Expand items
- **Space**: Refresh device list (Config Mode only)

#### Synth Mode Controls
- **W**: Toggle waveform (Sine → Square → Triangle)
- **↑/↓**: Adjust volume
- **←/→**: Adjust filter cutoff frequency
- **Q/A**: Increase/Decrease resonance
- **E/D**: Increase/Decrease attack time
- **R/F**: Increase/Decrease decay time
- **T/G**: Increase/Decrease intensity

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

#### Synth Mode *(NEW in v1.0.1)*
- Monophonic synthesizer (plays one note at a time)
- Real-time MIDI input with audio synthesis
- Visual controls for all synth parameters
- **Oscillator**: Choose between sine, square, or triangle waveforms
- **Mixer**: Control output volume
- **Filter**: Low-pass filter with cutoff (100Hz-5000Hz) and resonance controls
- **Envelope**: Shape sound with attack, decay, and intensity parameters
- Live parameter adjustment while playing

## Project Structure

```
acordes/
├── main.py                      # Application entry point
├── config_manager.py            # Configuration persistence
├── components/                  # UI widgets
│   ├── piano_widget.py          # Visual piano keyboard
│   ├── chord_display.py         # Chord name display
│   ├── staff_widget.py          # Musical staff notation display
│   └── confirmation_dialog.py   # Quit confirmation
├── modes/                       # Screen modes
│   ├── config_mode.py           # MIDI device configuration
│   ├── piano_mode.py            # Real-time piano display
│   ├── compendium_mode.py       # Chord reference
│   └── synth_mode.py            # Synthesizer interface (NEW in v1.0.1)
├── midi/                        # MIDI handling
│   ├── device_manager.py        # Device detection
│   └── input_handler.py         # MIDI input processing
├── music/                       # Music theory and synthesis
│   ├── chord_detector.py        # Chord recognition (supports 9th, 11th, 13th chords)
│   ├── chord_library.py         # Chord database
│   └── synth_engine.py          # Audio synthesis engine (NEW in v1.0.1)
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
- **PyAudio**: Real-time audio I/O (optional, for Synth Mode)
- **NumPy**: Numerical computing for audio synthesis

## Troubleshooting

### Audio Not Available (Synth Mode)

If you see "Audio not available" in Synth Mode:

1. Install PyAudio:
   ```bash
   pip install pyaudio
   ```

2. On Windows, you may need to install it via pre-built wheels:
   ```bash
   pip install pipwin
   pipwin install pyaudio
   ```

3. On Linux:
   ```bash
   sudo apt-get install portaudio19-dev python3-pyaudio
   pip install pyaudio
   ```

4. On macOS:
   ```bash
   brew install portaudio
   pip install pyaudio
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
