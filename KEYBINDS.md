# Keyboard Shortcuts

## Global Navigation

| Key | Action |
|---|---|
| **1** | Switch to Piano Mode |
| **2** | Switch to Compendium Mode |
| **3** | Switch to Synth Mode |
| **4** | Switch to Metronome Mode |
| **5** | Switch to Tambor (Drum Machine) Mode |
| **C** | Switch to Config Mode |
| **Escape** | Quit application (with confirmation) |

---

## Config Mode

| Key | Action |
|---|---|
| **Tab** | Focus to next section (MIDI devices ↔ Velocity curves) |
| **Shift+Tab** | Focus to previous section |
| **↑ / ↓** | Navigate list items |
| **Space** | Select MIDI device or Velocity curve |
| **R** | Refresh MIDI device list |
| **Escape** | Close Config Mode |

---

## Piano Mode

| Key | Action |
|---|---|
| **Arrow Keys** | Navigate the displayed tree (when in Compendium submode) |
| **Enter** | Expand / collapse tree items |
| **Space** | Play selected chord (Compendium only) |
| **E** | Expand all tree items (Compendium only) |

---

## Compendium Mode

| Key | Action |
|---|---|
| **Arrow Keys** | Navigate |
| **Enter** | Select / expand |
| **Space** | Play selected chord |
| **E** | Expand all |

---

## Metronome Mode

| Key | Action |
|---|---|
| **P / Space** | Start / stop metronome |
| **↑ / ↓** | Increase / decrease tempo (BPM) |
| **← / →** | Cycle through time signatures |

---

## Synth Mode — Presets & Utility

| Key | Action |
|---|---|
| **,** (comma) | Previous preset |
| **.** (period) | Next preset |
| **N** | Open Factory Presets browser |
| **Ctrl+N** | Save current patch as new preset |
| **Ctrl+S** | Overwrite currently loaded preset |
| **-** (minus) | Randomize all parameters |
| **Space** | Panic — silence all voices immediately |

---

## Synth Mode — Focus Mode Navigation

Press **Enter** to enter focus mode. In focus mode, a parameter cell is highlighted and can be adjusted.

| Key | Action |
|---|---|
| **Enter** | Enter / exit focus mode |
| **Escape** | Exit focus mode |
| **W** | Move cursor up |
| **S** | Move cursor down |
| **A** | Move cursor left |
| **D** | Move cursor right |
| **Q** | Decrease focused parameter |
| **E** | Increase focused parameter |
| **Shift+−** (Shift+Minus) | Randomize focused parameter only |
| **Alt+←** | Decrease focused parameter (alternative) |
| **Alt+→** | Increase focused parameter (alternative) |

---

## Synth Mode — Legacy Keys (Unfocused, No MIDI Keyboard Needed)

These keys work when **not** in focus mode. Useful for quick tweaks without a MIDI keyboard.

| Key | Action |
|---|---|
| **Q / W** | Octave down / up |
| **E / D** | Filter cutoff down / up |
| **R / F** | Resonance down / up |
| **T / G** | Attack time down / up |
| **Y / H** | Decay time down / up |
| **U / J** | Sustain level down / up |
| **I / K** | Release time down / up |
| **O / L** | Filter EG Amount down / up |
| **P / ;** | Filter EG Attack down / up |
| **[ / ]** | Master volume down / up |
| **↑ / ↓** | Amp level up / down |

---

## Tambor Mode (Drum Machine)

| Key | Action |
|---|---|
| **Space / P** | Play / stop pattern |
| **↑ / ↓** | Increase / decrease BPM |
| **← / →** | Navigate patterns or select drums |
| **Enter** | Select / edit |
| **S** | Toggle solo on selected drum |
| **M** | Toggle mute on selected drum |
| **F** | Open Fill pattern browser |
| **H** | Toggle humanization |
| **T** | Cycle timing modes (straight / swing / shuffle) |

---

## MIDI Controller Support

The synth responds to physical MIDI controllers:

- **MIDI Notes**: All note-on/note-off messages (velocity-sensitive)
- **Pitch Bend**: ±2 semitones (standard MIDI pitch bend wheel)
- **Modulation Wheel (CC1)**: Modulation control (ready for LFO routing)
- **Velocity Curves**: Selected in Config Mode, applied to all MIDI note velocities

---

## Focus Mode Details

Focus mode provides precise, arrow-key based parameter editing with exponential acceleration:
- Hold a key down to continuously adjust — the adjustment rate **accelerates** after ~1 second
- Fast taps produce small increments (1%)
- Sustained holds produce larger jumps (up to 2× speed)
- This gives you both precision and speed without needing a mouse

### Example: Adjusting Filter Cutoff in Focus Mode
1. Press **Enter** to enter focus mode (selected cell highlights)
2. Press **D** to move right into the FILTER section
3. Press **E** repeatedly to move down to the "Cutoff" parameter
4. Press **E** once → cutoff increases by 1%
5. Hold **E** for 2 seconds → cutoff increases smoothly at 2× speed
6. Release **E** to stop
7. Press **Escape** or **Enter** to exit focus mode

---

## Preset Naming

When you save a new preset with **Ctrl+N**, Acordes automatically generates a random musical name:
- Format: adjective + noun (e.g., *"amber reed"*, *"escuro sino"*, *"vazio echo"*)
- Names drawn from English, Portuguese, German, and French word banks
- Over 4 million unique combinations
- You can overwrite the name when prompted

---

## Special Notes

- **Config Mode Velocity Curve**: The velocity curve you select in Config Mode applies to **all** MIDI input across all modes (Piano, Synth, Compendium)
- **Shared BPM**: The Metronome and Arpeggiator share the same BPM setting — change it in either mode and both update
- **Preset Persistence**: The last preset you loaded is automatically restored when you restart the app
- **Synth State**: All synth parameter tweaks are auto-saved to disk, even if you don't save a preset
