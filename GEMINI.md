# GEMINI - Acordes Project

This document provides a comprehensive overview of the Acordes project, intended to be used as a context for AI-assisted development.

## 1. Project Overview

**Acordes** is a terminal-based MIDI piano application built in Python. It provides a rich, interactive Textual User Interface (TUI) for musicians and developers.

The application's core purpose is to visualize MIDI input in real-time, offering several modes for different musical tasks.

### Key Features:

*   **Real-time Piano Visualizer**: A 3-octave piano keyboard that highlights notes as they are played on a connected MIDI device.
*   **Chord Detection**: Automatically identifies and displays the name of chords being played, including complex voicings and inversions.
*   **Musical Staff Notation**: Renders played notes on both Treble and Bass clefs.
*   **Monophonic Synthesizer**: A built-in synth with multiple waveforms (sine, square, triangle), filter controls (cutoff, resonance), and an ADSR envelope.
*   **Chord Compendium**: A reference library to look up various chord types across all keys.
*   **MIDI Device Management**: A configuration screen to select and switch between connected MIDI input devices. The selected device is saved in `config.json`.

### Architecture and Technology:

The project follows a modular architecture, with a clear separation of concerns.

*   **Framework**: [**Textual**](https://textual.textualize.io/) is used as the primary framework for building the TUI.
*   **MIDI Handling**:
    *   [**mido**](https://mido.readthedocs.io/): For handling MIDI messages (note on/off).
    *   [**python-rtmidi**](https://pypi.org/project/python-rtmidi/): The backend used by `mido` for real-time performance.
*   **Music Theory**:
    *   [**mingus**](https://bspaans.github.io/python-mingus/): A powerful library used for chord detection and other music theory calculations.
*   **Audio Synthesis**:
    *   [**PyAudio**](https://people.csail.mit.edu/hubert/pyaudio/): For real-time audio stream output.
    *   [**NumPy**](https://numpy.org/): For generating audio waveforms (sine, square, etc.).
    *   [**SciPy**](https://scipy.org/): Used for signal processing, likely in the filter implementation.
*   **Configuration**: A simple `config.json` file stores the user's selected MIDI device, managed by `config_manager.py`.

### Project Structure:

```
├── main.py              # Main application entry point (AcordesApp)
├── config_manager.py    # Manages config.json
├── components/          # Reusable UI widgets (Piano, Staff, Dialogs)
├── modes/               # Application screens (PianoMode, SynthMode, etc.)
├── midi/                # MIDI device management and input handling
├── music/               # Music theory logic (ChordDetector, SynthEngine)
├── run.bat/run.sh       # Convenience scripts for launching the app
└── requirements.txt     # Python dependencies
```

## 2. Building and Running

The project uses a standard Python virtual environment.

### Setup:

1.  **Create and activate a virtual environment:**
    *   **Windows:**
        ```cmd
        python -m venv venv
        venv\Scripts\activate
        ```
    *   **macOS/Linux:**
        ```bash
        python -m venv venv
        source venv/bin/activate
        ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Note: `requirements-windows.txt` exists but `requirements.txt` seems to be the main one.*

### Running the Application:

The easiest way to run the application is by using the provided scripts:

*   **Windows (Command Prompt):**
    ```cmd
    run.bat
    ```
*   **Windows (PowerShell):**
    ```powershell
    .\run.ps1
    ```
*   **macOS/Linux:**
    ```bash
    ./run.sh
    ```

Alternatively, you can run it directly with Python:

```bash
python main.py
```

### Testing:

There are no explicit test files (`test_*.py`) or a dedicated test runner configured in the project. Testing appears to be manual.

## 3. Development Conventions

Based on the source code, the following conventions are observed:

*   **Code Style**: The code generally follows **PEP 8** standards. It uses type hints (`typing` module) extensively.
*   **Docstrings**: All major classes and functions have clear docstrings explaining their purpose, arguments, and return values.
*   **Modularity**: The application is broken down into logical modules (`modes`, `components`, `midi`, `music`), promoting separation of concerns.
*   **UI and Logic Separation**:
    *   `modes/*` files define the layout and high-level UI interaction for each screen.
    *   `components/*` files contain the more detailed, reusable UI widgets (like the piano or staff).
    *   `music/*` and `midi/*` files contain the core backend logic, decoupled from the UI.
*   **State Management**: The main `AcordesApp` class holds the central application state and passes an `app_context` dictionary to its screens. This context includes shared objects like the `MIDIDeviceManager` and `ChordDetector`.
*   **Asynchronous Operations**: The app uses `set_interval` for polling MIDI messages, a common pattern in Textual for handling real-time events without blocking the UI.
