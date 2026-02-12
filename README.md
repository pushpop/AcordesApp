<img width="698" height="485" alt="image" src="https://github.com/user-attachments/assets/52cd7352-ebd7-45ea-8079-8854dd3f7cd8" />

# Acordes - MIDI Piano TUI Application

A terminal-based MIDI piano application with real-time visualization and chord detection.


## Features

- **Config Mode**: Display and select MIDI devices connected to your system
- **Piano Mode**: Real-time visual piano keyboard (3 octaves) showing notes and chord detection
- **Chord Compendium**: Reference guide with all chord types across all musical keys

## Requirements

- Python 3.8+
- MIDI input device (MIDI keyboard, controller, or virtual MIDI device)

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

- **Tab**: Switch between modes (Config → Piano → Compendium → Config)
- **Escape**: Quit application (with confirmation dialog)
- **Arrow Keys**: Navigate within each mode
- **Enter**: Select/Expand items
- **Space**: Refresh device list (Config Mode only)

### Modes

#### Config Mode
- View all available MIDI input devices
- Select a device to use for Piano Mode
- Press Space to refresh the device list

#### Piano Mode
- Visual 3-octave piano keyboard (C4-B5)
- Real-time note highlighting
- Automatic chord detection
- Displays currently pressed notes and detected chords

#### Compendium Mode
- Browse complete chord library
- All 12 keys (C through B)
- 15+ chord types per key
- View chord notes for reference

## Project Structure

```
acordes/
├── main.py                      # Application entry point
├── config_manager.py            # Configuration persistence
├── components/                  # UI widgets
│   ├── piano_widget.py          # Visual piano keyboard
│   ├── chord_display.py         # Chord name display
│   └── confirmation_dialog.py   # Quit confirmation
├── modes/                       # Screen modes
│   ├── config_mode.py           # MIDI device configuration
│   ├── piano_mode.py            # Real-time piano display
│   └── compendium_mode.py       # Chord reference
├── midi/                        # MIDI handling
│   ├── device_manager.py        # Device detection
│   └── input_handler.py         # MIDI input processing
├── music/                       # Music theory
│   ├── chord_detector.py        # Chord recognition (supports 9th, 11th, 13th chords)
│   └── chord_library.py         # Chord database
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

## Troubleshooting

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
