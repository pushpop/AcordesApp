# Gamepad Controller Reference (v1.10.0 - Grasp)

## Overview

Acordes now features **full Xbox-style gamepad controller support** across all platforms:
- **Windows**: XInput API (Xbox 360, Xbox Elite, 3rd-party XInput controllers)
- **Linux (x86_64 & ARM)**: Evdev direct input (/dev/input/event*)
- **macOS**: Pygame controller system
- **Raspberry Pi / OStra**: Full support via evdev

All modes are fully navigable with the controller. No keyboard required.

---

## Global Controls (Always Available)

These button combinations work from any mode:

| Action | Button Combo | Effect |
|--------|---|---|
| **Go to Main Menu** | START (press alone) | Jump to main menu from any mode |
| **Go Back** | BACK_BTN (press alone) | Navigate to previous mode |
| **Panic / All Notes Off** | LB + RB (hold together) | Emergency silence (all synth voices release) |
| **Open Config** | START + BACK_BTN (hold together) | Open audio/MIDI/device configuration |

---

## Main Menu

| Action | Input | Effect |
|--------|-------|--------|
| **Navigate Left/Right** | DPAD_LEFT / DPAD_RIGHT | Cycle between menu buttons |
| **Select Mode** | A (CONFIRM) | Enter the highlighted mode (Piano, Compendium, Synth, Metronome, Tambor) |
| **Quit Application** | B (BACK) | Open quit confirmation dialog |

---

## Piano Mode

| Action | Input | Effect |
|--------|-------|--------|
| **Play Notes** | MIDI Keyboard | Play incoming MIDI notes (synth shows the piano visualization) |
| **Navigate/Scroll** | DPAD (all directions) | Scroll chord display and staff notation |
| **Return to Main Menu** | START (press alone) | Go to main menu |
| **Go Back** | BACK_BTN (press alone) | Return to previous mode |

---

## Compendium Mode (Music Theory Reference)

| Action | Input | Effect |
|--------|-------|--------|
| **Expand/Collapse** | A (CONFIRM) | Expand or collapse highlighted chord/scale/instrument category |
| **Play Chord/Item** | X (ACTION_1) | Play the currently highlighted item (audible preview) |
| **Expand All** | Y (ACTION_2) | Expand all categories in the browser tree |
| **Navigate Tree** | DPAD_UP / DPAD_DOWN | Move selection up/down in the chord browser |
| **Scroll Horizontally** | DPAD_LEFT / DPAD_RIGHT | Scroll details panel (if wider than display) |
| **Return to Main Menu** | START | Go to main menu |
| **Go Back** | BACK_BTN | Return to previous mode |

---

## Config Mode

| Action | Input | Effect |
|--------|-------|--------|
| **Navigate Within List** | DPAD_UP / DPAD_DOWN | Move cursor up/down within the active list |
| **Cycle Between Sections** | LB / RB | Move to previous/next configuration section (Backend → Audio → Buffer → MIDI → Velocity → Backend) |
| **Select Item** | A (CONFIRM) | Select the highlighted item (applies the selection) |
| **Close Config** | B (BACK) or BACK_BTN | Close config mode and return to the previous mode |
| **Refresh Devices** | Y (ACTION_2) | Manually refresh all device lists (audio, MIDI) |

**Config Sections** (in tab-cycle order):
1. Audio Backend (WASAPI, DirectSound, ASIO on Windows; ALSA/PulseAudio on Linux; Core Audio on macOS)
2. Audio Output Device
3. Buffer Size
4. MIDI Input Device
5. Velocity Curve

---

## Synth Mode (Parameter Editing & Preset Browser)

### Parameter Editing

| Action | Input | Effect |
|--------|-------|--------|
| **Navigate Parameters** | DPAD_UP / DPAD_DOWN / DPAD_LEFT / DPAD_RIGHT | Move focus between the 8 synth sections (OSC, Filter, Filter EG, Amp EG, LFO, Chorus, FX, Arpeggio) and within parameters |
| **Adjust Parameter** | LT / RT (Left/Right Trigger Axes) | Fine-adjust the currently focused parameter (↓ decreases, ↑ increases) |
| **Enter/Exit Focus Mode** | A (CONFIRM) | Toggle focus mode for the focused parameter (WASD-style cursor + Q/E adjustment in keyboard mode) |
| **Randomize Focused Param** | ACTION_2 (Y) | Generate a random value for the currently focused parameter |
| **Randomize All Params** | LB + ACTION_2 (Y combo) | Generate a complete random preset and suggest a musical name |
| **Panic** | LB + RB | All notes off (clean release of all 8 voices) |

### Preset Navigation

| Action | Input | Effect |
|--------|-------|--------|
| **Previous Preset** | LB (press alone) | Load the previous preset in the list |
| **Next Preset** | RB (press alone) | Load the next preset in the list |
| **Open Preset Browser** | RB + A combo | Open the factory preset browser (128 presets, 8 categories) |
| **Save Current Preset** | *(Keyboard only)* | Press S to save as new preset |

### General Navigation

| Action | Input | Effect |
|--------|-------|--------|
| **Return to Main Menu** | START | Go to main menu |
| **Go Back** | BACK_BTN | Return to previous mode |

---

## Metronome Mode

| Action | Input | Effect |
|--------|-------|--------|
| **Play/Stop** | A (CONFIRM) or X (ACTION_1) | Toggle metronome playback |
| **Increase Tempo** | DPAD_UP | Increment BPM by 1 |
| **Decrease Tempo** | DPAD_DOWN | Decrement BPM by 1 |
| **Increase Tempo (Fast)** | RB | Increment BPM by 10 |
| **Decrease Tempo (Fast)** | LB | Decrement BPM by 10 |
| **Change Time Signature** | DPAD_LEFT / DPAD_RIGHT | Cycle through available time signatures (2/4, 3/4, 4/4, 6/8, etc.) |
| **Return to Main Menu** | START | Go to main menu |
| **Go Back** | BACK_BTN | Return to previous mode |

**Note**: BPM is shared with Arpeggiator and Tambor drum machine.

---

## Tambor Mode (16-Step Drum Sequencer)

### Navigation

| Action | Input | Effect |
|--------|-------|--------|
| **Navigate Grid** | DPAD_UP / DPAD_DOWN / DPAD_LEFT / DPAD_RIGHT | Move cursor around the 16-step sequencer grid (horizontal steps, vertical drums) |
| **Toggle Step** | A (CONFIRM) | Activate/deactivate the currently highlighted step |
| **Play/Stop Sequencer** | X (ACTION_1) | Start or stop pattern playback |
| **Randomize Drum Sound** | Y (ACTION_2) | Generate random parameters for the currently selected drum |

### Pattern Management

| Action | Input | Effect |
|--------|-------|--------|
| **Previous Pattern** | LB | Load the previous pattern (1–64) |
| **Next Pattern** | RB | Load the next pattern |
| **Open Pattern Selector** | L3 (Left Stick Click) | Choose a pattern from the list of 64 slots |

### Drum Editing

| Action | Input | Effect |
|--------|-------|--------|
| **Edit Drum Sound** | R3 (Right Stick Click) | Open drum editor for the currently selected drum with full synth parameter control |
| **Toggle Drum Mute** | LT | Mute the drum in the selected row (synth voice remains available) |
| **Toggle Drum Solo** | RT | Solo the drum in the selected row (all others muted) |

### Fill Patterns

| Action | Input | Effect |
|--------|-------|--------|
| **Open Fill Selector** | Y (ACTION_2) | Choose a fill pattern or "None" (16 built-in fills + random generation) |

### General Navigation

| Action | Input | Effect |
|--------|-------|--------|
| **Return to Main Menu** | START | Go to main menu |
| **Go Back** | BACK_BTN | Return to previous mode |

---

## Button Mapping Reference

### Xbox-Style Controller Layout

```
                 Y (ACTION_2)
                    |
    LB ------- X (ACTION_1) ------- RB
     |              |              |
     |    DPAD      |      RStick  |
     |      |   A(CONFIRM)   |     |
    LT --  Start ----+---- Back --- RT
             |       |      |
         Back_Btn - B(BACK)
```

### Button Definitions

**Action Buttons**:
- **A** (CONFIRM): Select, activate, enter
- **B** (BACK): Cancel, go back, exit
- **X** (ACTION_1): Context-specific action (play chord in compendium, play drum in tambor)
- **Y** (ACTION_2): Alternate action (randomize, expand all)

**Shoulder Buttons**:
- **LB** (Left Bumper): Previous, decrease, decrement
- **RB** (Right Bumper): Next, increase, increment
- **LT** (Left Trigger): Left stick axis input, mute drum
- **RT** (Right Trigger): Right stick axis input, solo drum

**D-Pad**:
- **DPAD_UP**: Navigate up, increase
- **DPAD_DOWN**: Navigate down, decrease
- **DPAD_LEFT**: Navigate left, previous
- **DPAD_RIGHT**: Navigate right, next

**Special Buttons**:
- **START**: Jump to main menu globally, or close screens with autoreturn
- **BACK_BTN**: Go back to previous mode (distinct from B button)
- **L3** / **R3**: Left/Right stick click (Tambor pattern/drum editor)

---

## Advanced Features

### Combo Detection

Holding multiple buttons simultaneously performs special actions:
- **LB + RB**: Panic (all notes off from any mode)
- **START + BACK_BTN**: Open config from any mode
- **RB + A** (Synth): Open factory preset browser
- **LB + Y** (Synth): Randomize all parameters

The combo system checks the most specific combo first, so `START + BACK_BTN` won't also trigger the individual START action.

### Axis Input (Trigger & Stick)

**Trigger Axes** (Synth Mode):
- **LT / RT**: Adjust the focused synth parameter
  - LT (negative): Decrease value
  - RT (positive): Increase value
  - Mapped to parameter down/up actions

**Stick Clicks**:
- **L3** (Left Stick Press): Pattern selector in Tambor
- **R3** (Right Stick Press): Drum editor in Tambor

---

## Platform-Specific Notes

### Windows
- **Standard Support**: Xbox 360, Xbox One, Xbox Elite 2 (all XInput-compatible)
- **Other Controllers**: XBOX-compatible or generic XInput gamepads work seamlessly
- **Backend**: Native XInput via ctypes (no SDL overhead, no keyboard injection issues)
- **Full Screen Recommended**: Windows Terminal gamepad focus navigation can interfere; run in full-screen mode for best experience

### Linux (x86_64 & ARM)
- **Supported Controllers**: Any controller with `/dev/input/event*` support (Xbox, PS4, generic gamepads with xpad module)
- **Setup**:
  - Install xpad module: `sudo apt install xpadneo` or `sudo modprobe xpad`
  - Bluetooth pairing: Standard Linux Bluetooth utilities
  - Hot-plugging supported
- **Backend**: Evdev direct input (/dev/input/event*)

### Raspberry Pi / OStra (ARM)
- **Supported Controllers**: Same as Linux x86_64
- **Performance**: Optimized controller polling with minimal latency
- **User Group**: Add user to `input` group to avoid sudo requirement:
  ```bash
  sudo usermod -a -G input $(whoami)
  ```

### macOS
- **Supported Controllers**: Xbox, PS4, MFi controllers
- **Backend**: Pygame controller system
- **Native Support**: CoreController framework via Pygame

---

## Troubleshooting

### Controller Not Detected

**Windows**:
- Ensure the controller is connected via USB or wireless dongle
- Update Xbox controller drivers from Windows Update
- If using a third-party XInput controller, install manufacturer drivers

**Linux**:
- Check device: `ls /dev/input/event*`
- Load xpad module: `sudo modprobe xpad`
- Check permissions: `ls -l /dev/input/event*` (user must be in `input` group)
- Bluetooth: Pair using `bluetoothctl`

**macOS**:
- Check System Preferences → Bluetooth
- Ensure controller is in pairing mode

### Buttons Not Responding

1. Close and reopen the app
2. Check if the controller is recognized: Look for "[gamepad] controller connected" in stderr
3. If using wireless, ensure the receiver/dongle is powered and within range
4. Try a different USB port or re-seat the wireless receiver

### Jerky or Delayed Input

- Close other applications consuming CPU
- On ARM (Raspberry Pi), ensure the CPU governor is set to `performance` (automatic via launcher)
- Check for interference: Move wireless receiver away from WiFi/Bluetooth sources

---

## Quick Reference Card

Print this or keep it handy:

```
GLOBAL
  START              → Main Menu
  BACK_BTN           → Go Back
  LB + RB            → Panic (all notes off)
  START + BACK_BTN   → Open Config

MAIN MENU
  DPAD_LEFT/RIGHT    → Select Mode
  A                  → Enter Mode
  B                  → Quit App

SYNTH MODE
  DPAD_UP/DOWN/LEFT/RIGHT  → Navigate Parameters
  LT / RT            → Adjust Parameter Value
  A                  → Enter/Exit Focus Mode
  X                  → Panic
  Y                  → Randomize Focused Param
  LB                 → Previous Preset
  RB                 → Next Preset
  RB + A             → Preset Browser
  LB + Y             → Randomize All

COMPENDIUM MODE
  DPAD_UP/DOWN       → Browse Tree
  A                  → Expand/Collapse
  X                  → Play Chord

METRONOME MODE
  A / X              → Play/Stop
  DPAD_UP/DOWN       → Tempo ±1
  LB / RB            → Tempo ±10
  DPAD_LEFT/RIGHT    → Change Time Signature

TAMBOR MODE
  DPAD_UP/DOWN/LEFT/RIGHT  → Navigate Grid
  A                  → Toggle Step
  X                  → Play/Stop Sequencer
  LB / RB            → Previous/Next Pattern
  L3                 → Pattern Selector
  R3                 → Drum Editor
  Y                  → Randomize Drum
  LT / RT            → Mute / Solo Drum

CONFIG MODE
  DPAD_UP/DOWN       → Navigate Within List
  LB / RB            → Cycle Sections
  A                  → Select Item
  B / BACK_BTN       → Close Config
  Y                  → Refresh Devices
```

---

## Platform-Specific Notes

### Raspberry Pi / OStra with Xbox Controllers

**Boot-Time Initialization**: On Raspberry Pi, the Xbox controller is fully initialized by `run-ostra.sh` before Acordes launches. The launcher performs a USB power cycle on boot (deauthorize/reauthorize the device via `/sys/bus/usb/devices/X/authorized`) which ensures the xpad driver completes its GIP handshake. This prevents the controller from entering pairing/search mode (blinking light) and guarantees the controller is ready when the app starts.

**Auto-Reconnect**: If the controller is disconnected during a session, `poll()` automatically attempts to reconnect every 3 seconds. Simply unplug and replug the USB cable — the app will detect and reconnect within seconds without restarting.

**Keepalive**: On ARM, a periodic SYN_REPORT is written to the device (every 30 seconds) to signal active usage and prevent controller timeout.

---

## Supported Controllers

**Fully Tested & Supported**:
- Xbox 360 (wired)
- Xbox One (wired)
- Xbox Elite 2 (wired)
- Generic XInput gamepads

**Known Compatible**:
- PlayStation 4 DualShock 4 (via xinput wrapper on Windows; native on Linux/macOS)
- 8BitDo controllers (when in XInput mode)
- SCUF/FPS controllers

**Note**: Pygame-based backend (macOS, Linux) supports any SDL2-compatible controller.

---

*For keyboard shortcuts, see [KEYBINDS.md](KEYBINDS.md).*
