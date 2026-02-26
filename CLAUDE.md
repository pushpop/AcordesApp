# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# Windows (auto-creates venv, installs deps on first run)
run.bat           # Command Prompt
.\run.ps1         # PowerShell

# Linux / macOS
./run.sh

# Direct (after venv exists)
venv\Scripts\python.exe main.py   # Windows
./venv/bin/python main.py         # Linux/macOS
```

**Python version:** Use 3.11 or 3.12. PyAudio and python-rtmidi have no pre-built wheels for 3.13+. The Windows launchers auto-select 3.12 via the `py` launcher when available.

There are no tests, no linting config, and no CI pipeline.

## Architecture

### Entry point & mode switching

`main.py` owns the Textual `App` and `MainScreen`. All shared components (synth engine, MIDI handler, config, chord library) are created here and passed into modes via constructor parameters or the `app_context` dict.

Mode switching happens in `MainScreen._switch_mode()`: it calls `synth_engine.all_notes_off()`, removes all children from the `#content-area` container, then mounts the new mode widget. Modes are fully unmounted/remounted on every switch — there is no caching.

### Modes (`modes/`)

Each mode is a Textual `Widget` subclass. Modes use `on_mount()` / `on_unmount()` for lifecycle. Modes that need MIDI input call `midi_handler.set_callbacks(...)` in `on_mount` to register note-on/note-off/pitch-bend handlers, and must clear them in `on_unmount`.

**Widget lifecycle:** `compose()` yields child widgets in order (determines initial layout), then `on_mount()` is called (can mount additional widgets or start timers). Set `can_focus = True` and define `BINDINGS` list if the mode needs keyboard input; `_switch_mode()` will call `widget.focus()` after mounting to activate key bindings.

Key modes:
- **`synth_mode.py`** — The most complex mode. Manages 8 UI sections (OSC, FILTER, ENVELOPE, LFO, CHORUS, FX, ARPEGGIO, MIXER) rendered as a parameter grid. Has two input sub-modes: *focus mode* (WASD cursor + Q/E value change + `_` randomize focused param) and *legacy mode* (letter keys mapped to individual params). All parameter changes go through `_push_params_to_engine()` → `synth_engine.update_parameters(**kwargs)`.
- **`piano_mode.py`** — Visualises the MIDI keyboard, runs chord detection, also drives synth.
- **`metronome_mode.py`** — Shares BPM with the arpeggiator via `config_manager.get_bpm()` / `set_bpm()`.
- **`tambor/tambor_mode.py`** — TR-909-style drum machine (16-step sequencer, 8 drum sounds, pattern management, fills, humanize). Integrated from standalone Tambor project. Uses the shared Acordes `SynthEngine` to generate drum sounds via MIDI triggers. Pattern playback enqueues note-on/off events to `synth_engine.midi_event_queue` for sample-accurate timing. BPM syncs with metronome via `config_manager`.

### MIDI flow

```
MIDI hardware
  → mido/python-rtmidi (mido.open_input)
  → MIDIInputHandler.poll_messages()   [called on a Textual timer in each mode]
  → mode callbacks (_on_note_on / _on_note_off)
  → SynthEngine.note_on() / note_off() [enqueues to midi_event_queue]
  → _audio_callback() [PyAudio thread, drains queue each buffer]
```

`MIDIInputHandler` (`midi/input_handler.py`) is a thin wrapper around `mido`. It maintains an `active_notes` set (protected by `notes_lock`) and dispatches to registered callbacks. Polling is non-blocking (`iter_pending()`).

### Audio engine (`music/synth_engine.py`)

All parameter changes from the UI thread are enqueued via `synth_engine.update_parameters(**kwargs)` and applied at the top of `_audio_callback()` by `_process_midi_events()`. **Never write directly to engine attributes from the UI thread** — this causes data races.

Signal chain per buffer (inside `_audio_callback`):
1. Drain MIDI event queue (param updates, note on/off, all-notes-off)
2. LFO tick (shape-aware: SIN/TRI/SQR/S&H → routes to VCO/VCF/VCA)
3. Arpeggiator clock (sample-accurate, audio-thread driven)
4. Voice loop: oscillator → filter (ladder or SVF) → envelope → onset ramp → DC blocker → pan → stereo mix
5. Chorus DSP (BBD-style ring buffer, bypass if `chorus_mix == 0`)
6. Delay DSP (stereo feedback loop, bypass if `delay_mix == 0`)
7. Filter-switch anti-click ramp
8. Randomize mute gate
9. `tanh` soft-clip + master volume → int16 PCM output

FX tails (delay echoes, chorus) continue playing after all voices release via `_fx_tail_samples` counter set in `_trigger_note()`. `all_notes_off()` resets it to 0 for immediate silence.

The audio callback runs at elevated OS priority (`SetPriorityClass` on Windows, `SCHED_FIFO` on Linux, `THREAD_TIME_CONSTRAINT_POLICY` on macOS).

### Preset system (`music/preset_manager.py`, `presets/`)

Presets are JSON files in `presets/`. `PresetManager` loads all `.json` files; factory presets are listed first (alphabetically), then user presets. Saving creates a new file with a randomly generated musical name. `config_manager` persists the last-used preset name across restarts.

### Config persistence (`config_manager.py`)

`ConfigManager` loads/saves `config.json` (gitignored). Stores: selected MIDI device, last synth preset name, full synth parameter state (`synth_state`), and shared metronome/arpeggiator BPM. Every setter writes to disk immediately.

### Pattern system (Tambor - `modes/tambor/music/`)

Patterns are JSON files stored in `presets/tambor/` (separate from synth presets). Each pattern file contains drum step data, BPM, pre-scale, mute/solo state, and humanize settings. `PatternManager` handles file I/O; `PatternSaver`/`PatternLoader` use a background thread pool for non-blocking saves/loads to avoid UI freezes during file I/O. The UI thread enqueues save requests; the background thread processes them asynchronously.

## Key conventions

- **Thread safety:** UI thread ↔ audio thread communicate exclusively through `synth_engine.midi_event_queue`. The `param_update` event type is the only safe way to change synth parameters mid-playback.
- **Textual key bindings:** Textual 0.75+ maps Shift+Minus to the key name `"underscore"` (not `"shift+minus"`). Special characters follow Textual's `_character_to_key()` translation.
- **Textual CSS selectors:** ID selectors (`#help-bar`) and element selectors (`TamborMode > HelpBar`) behave differently in widget layout. Yielding a widget in `compose()` places it in the parent's children list in order; re-mounting widgets via `mount()` appends them to the end. Use ID selectors for styling that should be independent of parent type.
- **`requirements-windows.txt`** is an outdated stub — `requirements.txt` is the authoritative file for all platforms.
- **`venv/`** is gitignored. The launcher scripts recreate it automatically.
