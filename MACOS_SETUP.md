# Acordes - macOS Setup Guide

This guide will help you set up and run Acordes on macOS.

## Prerequisites

- macOS 10.13 or later
- Python 3.8 or higher
- A MIDI input device (MIDI keyboard, controller, or virtual MIDI device)

## Installation

### Step 1: Verify Python Installation

Open Terminal and check if Python 3.8+ is installed:

```bash
python3 --version
```

If Python is not installed, download it from [python.org](https://www.python.org/downloads/) or install via Homebrew:

```bash
brew install python3
```

### Step 2: Navigate to Project Directory

```bash
cd /path/to/acordes
```

### Step 3: Create Virtual Environment

```bash
python3 -m venv venv
```

### Step 4: Activate Virtual Environment

```bash
source venv/bin/activate
```

You should see `(venv)` appear in your terminal prompt.

### Step 5: Install Dependencies

```bash
pip install -r requirements.txt
```

**Important:** Use `requirements.txt`, NOT `requirements-windows.txt`

## Running the Application

### Option 1: Using the Shell Script (Recommended)

Make the script executable (first time only):

```bash
chmod +x run.sh
```

Run the application:

```bash
./run.sh
```

### Option 2: Direct Invocation

With the virtual environment activated:

```bash
python main.py
```

### Option 3: Without Activating Virtual Environment

```bash
./venv/bin/python main.py
```

## MIDI Setup on macOS

macOS uses **CoreMIDI** for MIDI device management, which works automatically with no additional configuration needed.

### Connecting Your MIDI Device

1. Connect your MIDI device to your Mac via USB or MIDI interface
2. macOS will automatically detect the device through CoreMIDI
3. Launch Acordes - your device should appear in the Config Mode

### Troubleshooting MIDI Devices

If your MIDI device doesn't appear:

1. **Check Audio MIDI Setup:**
   - Open `/Applications/Utilities/Audio MIDI Setup.app`
   - Click "Window" → "Show MIDI Studio"
   - Verify your device appears in the MIDI Studio window

2. **Restart the Device:**
   - Disconnect and reconnect the USB cable
   - Try a different USB port

3. **Check Permissions:**
   - Go to System Preferences → Security & Privacy → Privacy
   - Ensure Terminal (or your terminal app) has necessary permissions

## Application Controls

### Keyboard Shortcuts

- **1**: Switch to Piano Mode
- **2**: Switch to Compendium Mode
- **C**: Open Config Mode (MIDI device selection)
- **Escape**: Quit application (with confirmation)

### Config Mode

- **↑↓ Arrow Keys**: Navigate device list
- **Space**: Select device and close
- **R**: Refresh device list
- **Escape**: Close without changes

### Piano Mode

- Play notes on your MIDI keyboard to see:
  - Visual piano keyboard with real-time note highlighting
  - Automatic chord detection
  - Note names of pressed keys
  - Dynamic octave adjustment

### Compendium Mode

- **↑↓ Arrow Keys**: Navigate chord library
- **Enter**: Expand/collapse chord categories
- **Space**: Expand all categories

## Features

- **Real-time MIDI Input**: Responds instantly to your MIDI keyboard
- **Chord Detection**: Automatically identifies chords (triads, 7ths, 9ths, 11ths, 13ths)
- **Dynamic Octave Display**: Piano keyboard adjusts to show the octaves you're playing
- **Chord Reference Library**: Browse 180+ chords across all 12 keys
- **Visual Feedback**: Color-coded display with red highlighting for pressed keys

## Deactivating Virtual Environment

When you're done:

```bash
deactivate
```

## Uninstallation

To remove Acordes:

```bash
cd /path/to/acordes
rm -rf venv
cd ..
rm -rf acordes
```

## Support

If you encounter issues:

1. Ensure Python 3.8+ is installed
2. Verify your MIDI device works with Audio MIDI Setup
3. Check that all dependencies installed correctly
4. Try recreating the virtual environment

## Cross-Platform Notes

This application is fully cross-platform:
- The same codebase runs on macOS, Linux, and Windows
- No macOS-specific modifications needed
- CoreMIDI integration is automatic on macOS
- All features work identically across platforms

---

**Enjoy playing with Acordes!** 🎹
