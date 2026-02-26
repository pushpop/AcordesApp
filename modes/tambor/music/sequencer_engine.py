"""ABOUTME: Core sequencer engine for Tambor drum machine.
ABOUTME: Handles timing, step sequencing, drum triggering, and BPM synchronization."""

import threading
import time
from typing import Callable, Optional, Dict, List


class SequencerEngine:
    """
    Handles the timing and playback logic for the drum sequencer.

    Features:
    - Variable step count (1-32 steps)
    - BPM-synchronized timing
    - Variable note length per step (0.0-1.0 fraction of step duration)
    - Variable velocity per step (0-127)
    - Thread-safe operation with synth_engine
    - Callback-based step triggering for UI updates
    """

    def __init__(self, synth_engine, config_manager, num_steps: int = 16, bpm_callback: Optional[Callable[[], float]] = None):
        """
        Initialize the sequencer engine.

        Args:
            synth_engine: Acordes synth engine for audio output
            config_manager: Config manager for BPM and settings
            num_steps: Number of steps in the sequencer (1-32, default 16)
            bpm_callback: Optional callback function that returns current BPM (used instead of config_manager if provided)
        """
        self.synth_engine = synth_engine
        self.config_manager = config_manager
        self.bpm_callback = bpm_callback

        # Step configuration
        self.num_steps = max(1, min(32, num_steps))  # Clamp to 1-32
        self.current_step = 0

        # Playback state
        self.is_playing = False
        self.is_paused = False

        # Timing
        self._last_step_time = 0.0
        self._playback_timer = None

        # Callback for UI updates
        self.on_step_callback: Optional[Callable[[int], None]] = None

        # Track active notes for cleanup
        self._active_notes: Dict[int, float] = {}  # midi_note -> release_time
        self._note_timers: Dict[int, threading.Timer] = {}

        # Track mute state per drum (MIDI note)
        self.drum_mute_state: Dict[int, bool] = {}  # midi_note -> is_muted

    def set_step_callback(self, callback: Callable[[int], None]):
        """
        Set callback function called each step with current step number.

        Args:
            callback: Function(step_index) called when step advances
        """
        self.on_step_callback = callback

    def set_num_steps(self, num_steps: int):
        """
        Set the number of steps in the sequencer.

        Args:
            num_steps: New step count (will be clamped to 1-32)
        """
        self.num_steps = max(1, min(32, num_steps))

        # Reset step if out of bounds
        if self.current_step >= self.num_steps:
            self.current_step = 0

    def get_step_duration(self) -> float:
        """
        Calculate the duration of one step in seconds based on BPM.

        Returns:
            Duration of one 16th note step in seconds
        """
        # Use bpm_callback if provided (for Acordes integration), else fall back to config_manager
        if self.bpm_callback is not None:
            bpm = self.bpm_callback()
        else:
            bpm = self.config_manager.get_bpm()
        # 16th note = quarter note / 4
        # Quarter note = 60 / BPM seconds
        # So 16th note = 60 / (BPM * 4)
        return 60.0 / (bpm * 4)

    def start(self):
        """Start playback from current step."""
        if self.is_playing:
            return

        self.is_playing = True
        self.is_paused = False
        self.current_step = 0
        self._last_step_time = time.time()

    def stop(self):
        """Stop playback and reset to step 0."""
        self.is_playing = False
        self.is_paused = False
        self.current_step = 0
        self._all_notes_off()

    def pause(self):
        """Pause playback without resetting step."""
        self.is_paused = True
        self._all_notes_off()

    def resume(self):
        """Resume from paused state."""
        if self.is_playing and self.is_paused:
            self.is_paused = False
            self._last_step_time = time.time()

    def update(self):
        """
        Call this regularly to advance the sequencer.
        Should be called from Textual's set_interval timer.

        Returns:
            True if step advanced, False otherwise
        """
        if not self.is_playing or self.is_paused:
            return False

        # Check if enough time has passed for next step
        current_time = time.time()
        step_duration = self.get_step_duration()

        if current_time - self._last_step_time >= step_duration:
            self._advance_step()
            self._last_step_time = current_time
            return True

        return False

    def _advance_step(self):
        """Internal: Advance to next step and trigger callback."""
        # Advance step counter
        self.current_step = (self.current_step + 1) % self.num_steps

        # Call UI callback if registered
        if self.on_step_callback:
            self.on_step_callback(self.current_step)

    def trigger_drum(self, midi_note: int, velocity: int = 100, note_length: float = 0.5):
        """
        Trigger a drum sound.

        Args:
            midi_note: MIDI note number to trigger
            velocity: Note velocity (0-127, default 100)
            note_length: Duration as fraction of step (0.0-1.0, default 0.5)
        """
        # Clamp velocity
        velocity = max(0, min(127, velocity))
        note_length = max(0.0, min(1.0, note_length))

        # Send note_on to synth engine
        self.synth_engine.note_on(midi_note, velocity)

        # Track active note
        step_duration = self.get_step_duration()
        note_duration_seconds = step_duration * note_length
        release_time = time.time() + note_duration_seconds

        self._active_notes[midi_note] = release_time

        # Cancel existing timer for this note if any
        if midi_note in self._note_timers:
            self._note_timers[midi_note].cancel()

        # Schedule note_off
        timer = threading.Timer(
            note_duration_seconds,
            self._schedule_note_off,
            args=(midi_note,)
        )
        timer.daemon = True
        timer.start()
        self._note_timers[midi_note] = timer

    def _schedule_note_off(self, midi_note: int):
        """Internal: Send note_off for a specific MIDI note."""
        self.synth_engine.note_off(midi_note, velocity=0)

        # Clean up tracking
        if midi_note in self._active_notes:
            del self._active_notes[midi_note]
        if midi_note in self._note_timers:
            del self._note_timers[midi_note]

    def _all_notes_off(self):
        """Internal: Stop all active notes."""
        # Cancel all pending timers
        for timer in self._note_timers.values():
            timer.cancel()
        self._note_timers.clear()

        # Send all_notes_off to synth engine
        self.synth_engine.all_notes_off()
        self._active_notes.clear()

    def get_current_step(self) -> int:
        """Get the current step index (0-based)."""
        return self.current_step

    def set_current_step(self, step: int):
        """Set the current step index."""
        step = max(0, min(self.num_steps - 1, step))
        self.current_step = step

    def mute_drum(self, midi_note: int):
        """Mark a drum (by MIDI note) as muted - won't trigger when pattern plays."""
        self.drum_mute_state[midi_note] = True

    def unmute_drum(self, midi_note: int):
        """Mark a drum (by MIDI note) as unmuted."""
        self.drum_mute_state[midi_note] = False

    def is_drum_muted(self, midi_note: int) -> bool:
        """Check if a drum is currently muted."""
        return self.drum_mute_state.get(midi_note, False)

    def save_mute_state(self) -> Dict[int, bool]:
        """Save current mute state for later restoration (returns a copy)."""
        return self.drum_mute_state.copy()

    def restore_mute_state(self, state: Dict[int, bool]):
        """Restore mute state from a saved snapshot."""
        self.drum_mute_state = state.copy()

    def is_step_active(self, step_data) -> bool:
        """
        Check if a step has active note(s).

        Args:
            step_data: Step data dict with 'active' key

        Returns:
            True if step is active, False otherwise
        """
        if isinstance(step_data, dict):
            return step_data.get("active", False)
        elif isinstance(step_data, bool):
            return step_data
        return False

    def get_step_info(self, step_data) -> dict:
        """
        Get step information with defaults.

        Args:
            step_data: Step data (dict or bool for compatibility)

        Returns:
            Dictionary with 'active', 'velocity', 'note_length'
        """
        if isinstance(step_data, dict):
            return {
                "active": step_data.get("active", False),
                "velocity": step_data.get("velocity", 100),
                "note_length": step_data.get("note_length", 0.5),
            }
        else:
            # Backward compatibility for boolean patterns
            return {
                "active": bool(step_data),
                "velocity": 100,
                "note_length": 0.5,
            }

    def get_beat_position(self, step: int, pre_scale: int) -> tuple:
        """
        Calculate beat and position within beat for a given step.

        This is informational only and does not affect playback timing.

        Args:
            step: Step index (0-based)
            pre_scale: Steps per beat (1, 2, 4, 8, or 16)

        Returns:
            Tuple of (beat_number, position_in_beat)
        """
        beat = step // pre_scale
        position = step % pre_scale
        return (beat, position)
