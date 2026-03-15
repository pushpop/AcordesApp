# ABOUTME: Piano mode — real-time MIDI keyboard visualiser with chord detection and staff display.
# ABOUTME: Applies a dedicated piano-like sound on mount and restores the previous synth state on exit.
from textual.widget import Widget
from textual.containers import Vertical, Center
from textual.widgets import Label
from textual.message import Message
from typing import TYPE_CHECKING, Set

from components.piano_widget import PianoWidget
from components.chord_display import ChordDisplay
from components.staff_widget import StaffWidget
from components.header_widget import HeaderWidget

if TYPE_CHECKING:
    from midi.input_handler import MIDIInputHandler
    from music.chord_detector import ChordDetector
    from music.synth_engine import SynthEngine

# Piano-mode exclusive sound — applied on mount, restored on exit.
# Modelled after a bright acoustic piano: sine-based, fast attack, natural decay,
# moderate key tracking, no LFO/delay/chorus, arpeggiator off.
_PIANO_PARAMS: dict = {
    "waveform":       "sine",
    "octave":         0,
    "noise_level":    0.0,
    "amp_level":      0.88,
    "cutoff":         6000.0,
    "hpf_cutoff":     40.0,
    "resonance":      0.15,
    "hpf_resonance":  0.0,
    "key_tracking":   0.75,
    "attack":         0.004,
    "decay":          0.55,
    "sustain":        0.25,
    "release":        0.45,
    "rank2_enabled":  False,
    "rank2_waveform": "sine",
    "rank2_detune":   0.0,
    "rank2_mix":      0.0,
    "sine_mix":       0.0,
    "lfo_freq":       1.0,
    "lfo_vco_mod":    0.0,
    "lfo_vcf_mod":    0.0,
    "lfo_vca_mod":    0.0,
    "lfo_shape":      "sine",
    "lfo_target":     "all",
    "lfo_depth":      0.0,
    "delay_time":     0.25,
    "delay_feedback": 0.3,
    "delay_mix":      0.0,
    "chorus_rate":    0.5,
    "chorus_depth":   0.0,
    "chorus_mix":     0.0,
    "chorus_voices":  2,
    "arp_enabled":    False,
    "arp_mode":       "up",
    "arp_gate":       0.5,
    "arp_range":      1,
    "voice_type":     "poly",
    "feg_attack":     0.004,
    "feg_decay":      0.3,
    "feg_sustain":    0.0,
    "feg_release":    0.3,
    "feg_amount":     0.35,
}


class NoteEvent(Message):
    """Message sent when MIDI notes change."""

    def __init__(self, notes: Set[int]):
        super().__init__()
        self.notes = notes


class PianoMode(Widget):
    """Widget for real-time piano display and chord detection."""

    CSS = """
    PianoMode {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    #piano-section {
        layout: vertical;
        width: 100%;
        height: 43%;
        text-align: center;
        content-align: center middle;
        background: #1a1a1a;
        padding: 1;
    }

    #staff-section {
        width: 100%;
        height: 48%;
        align: center top;
        background: #0a0a0a;
        padding: 0;
    }

    #piano {
        width: 100%;
        height: auto;
        text-align: center;
        content-align: center middle;
        color: #ffffff;
        background: #1a1a1a;
    }

    #status {
        width: 100%;
        height: auto;
        content-align: center middle;
        padding: 1 0;
        color: #666666;
        text-style: italic;
    }

    #staff-display {
        width: auto;
        height: auto;
        content-align: center top;
        text-align: center;
        padding: 0;
        background: #0a0a0a;
    }

    #chord-display {
        width: auto;
        height: auto;
        min-height: 1;
        content-align: center middle;
        text-align: center;
        padding: 0 4;
        margin: 0;
        background: transparent;
    }
    """

    def __init__(self, midi_handler: 'MIDIInputHandler',
                 chord_detector: 'ChordDetector',
                 synth_engine: 'SynthEngine'):
        super().__init__()
        self.midi_handler = midi_handler
        self.chord_detector = chord_detector
        self.synth_engine = synth_engine
        self.piano_widget = None
        self.chord_display_widget = None
        self.staff_widget = None
        # Track last displayed note set — only redraw when it actually changes
        self._last_displayed_notes: Set[int] = set()
        # Snapshot of synth params captured on mount; restored when leaving piano mode
        self._saved_synth_params: dict = {}

    def compose(self):
        """Compose the piano mode layout."""
        # Header section
        self.header = HeaderWidget(
            title=self._get_acordes_ascii(),
            subtitle=self._get_status_text(),
            is_big=True,
            id="title-section"
        )
        yield self.header

        # Chord display section (above piano)
        with Center():
            self.chord_display_widget = ChordDisplay(id="chord-display")
            yield self.chord_display_widget

        # Piano section (middle - 43%)
        with Vertical(id="piano-section"):
            # Piano keyboard
            with Center():
                self.piano_widget = PianoWidget(id="piano")
                yield self.piano_widget

        # Staff section (bottom - 56%)
        with Vertical(id="staff-section"):
            # Musical staff
            with Center():
                self.staff_widget = StaffWidget(id="staff-display")
                yield self.staff_widget

    def on_mount(self):
        """Called when screen is mounted."""
        self._poll_timer = None
        self._register_midi_callbacks()

        # Snapshot the current synth state so we can restore it on exit,
        # then apply the dedicated piano sound exclusively for this mode.
        self._saved_synth_params = self.synth_engine.get_current_params()
        self.synth_engine.update_parameters(**_PIANO_PARAMS)

        # Initialize chord display
        if self.chord_display_widget:
            self.chord_display_widget.update_display(None, [])

        # Initialize staff display
        if self.staff_widget:
            self.staff_widget.update_notes(set())

        # Start polling for MIDI messages.
        # ARM: 30ms poll is enough for responsive MIDI and avoids waking the UI
        # thread (and grabbing the GIL) 100 times/sec, which causes audio xruns.
        import platform as _plat
        _poll_interval = 0.03 if _plat.machine() in ("armv7l", "aarch64") else 0.01
        self._poll_timer = self.set_interval(_poll_interval, self._poll_midi)

    def on_unmount(self):
        """Restore previous synth state when leaving Piano mode."""
        # Note: _switch_mode already called soft_all_notes_off() before unmounting.
        if self._saved_synth_params:
            self.synth_engine.update_parameters(**self._saved_synth_params)

    def _register_midi_callbacks(self):
        """Register MIDI callbacks with the MIDI handler."""
        self.midi_handler.set_callbacks(
            note_on=self._on_note_on,
            note_off=self._on_note_off,
        )

    def on_mode_pause(self):
        """Called by MainScreen when hiding this mode (widget caching).

        Restores the synth to its pre-piano state, stops the poll timer,
        and clears MIDI callbacks so no events fire while the mode is hidden.
        """
        if self._saved_synth_params:
            self.synth_engine.update_parameters(**self._saved_synth_params)
        self.midi_handler.set_callbacks(note_on=None, note_off=None)
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None

    def on_mode_resume(self):
        """Called by MainScreen when showing this cached mode again.

        Re-snapshots synth state, re-applies piano sound, re-registers
        MIDI callbacks, and restarts the poll timer.
        """
        self._saved_synth_params = self.synth_engine.get_current_params()
        self.synth_engine.update_parameters(**_PIANO_PARAMS)
        self._register_midi_callbacks()
        import platform as _plat
        _poll_interval = 0.03 if _plat.machine() in ("armv7l", "aarch64") else 0.01
        self._poll_timer = self.set_interval(_poll_interval, self._poll_midi)

    def _poll_midi(self):
        """Poll for MIDI messages."""
        if self.midi_handler.is_device_open():
            self.midi_handler.poll_messages()
            # Only redraw when the active note set actually changes
            active_notes = self.midi_handler.get_active_notes()
            if active_notes != self._last_displayed_notes:
                self._last_displayed_notes = active_notes
                self._update_display(active_notes)

    def _on_note_on(self, note: int, velocity: int):
        """Callback for note on events with velocity."""
        # Visual updates happen in _poll_midi
        # Play audio using synth engine
        self.synth_engine.note_on(note, velocity)

    def _on_note_off(self, note: int, velocity: int = 0):
        """Callback for note off events."""
        # Visual updates happen in _poll_midi
        # Stop audio using synth engine
        self.synth_engine.note_off(note, velocity)

    def _update_display(self, notes: Set[int]):
        """Update the piano and chord display."""
        # Update piano widget
        if self.piano_widget:
            self.piano_widget.update_notes(notes)

        # Detect and display chord
        if self.chord_display_widget:
            chord_name = self.chord_detector.detect_chord(notes)
            note_names = self.chord_detector.get_note_names(notes)
            self.chord_display_widget.update_display(chord_name, note_names)

        # Update musical staff
        if self.staff_widget:
            self.staff_widget.update_notes(notes)

    def _get_status_text(self) -> str:
        """Get status text based on MIDI connection."""
        if self.midi_handler.is_device_open():
            return "🎵 MIDI device connected - Play some notes!"
        else:
            return "⚠ No MIDI device connected - Select one in Config Mode"

    def _get_acordes_ascii(self) -> str:
        """Get the ACORDES ASCII art."""
        return """
   █████╗  ██████╗ ██████╗ ██████╗ ██████╗ ███████╗███████╗
  ██╔══██╗██╔════╝██╔═══██╗██╔══██╗██╔══██╗██╔════╝██╔════╝
  ███████║██║     ██║   ██║██████╔╝██║  ██║█████╗  ███████╗
  ██╔══██║██║     ██║   ██║██╔══██╗██║  ██║██╔══╝  ╚════██║
  ██║  ██║╚██████╗╚██████╔╝██║  ██║██████╔╝███████╗███████║
  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝
"""
