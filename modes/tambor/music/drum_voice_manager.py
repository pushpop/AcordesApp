"""ABOUTME: Drum Voice Manager - manages dedicated monophonic voices for each drum instrument.
ABOUTME: Ensures drums sound percussive and distinct by pre-allocating one voice per drum."""

from typing import Dict, Any, Optional
from .drum_presets import DRUM_PRESETS


class DrumVoiceManager:
    """
    Manages monophonic synthesis for drum instruments using pre-allocated synth voices.

    Each drum gets a dedicated voice that:
    - Is always monophonic (no polyphony/voice-stealing between drums)
    - Uses percussive envelope shapes (fast attack, controlled decay)
    - Maps to a fixed MIDI note for consistent routing
    - Has drum-specific synthesizer parameters (no polyphony artifacts)
    """

    def __init__(self, synth_engine: Any):
        """
        Initialize drum voice manager with shared synth engine.

        Args:
            synth_engine: Acordes SynthEngine instance for audio synthesis
        """
        self.synth_engine = synth_engine
        self.drum_voices: Dict[int, Dict[str, Any]] = {}
        self.midi_note_params: Dict[int, Dict[str, Any]] = {}  # Cache parameters by MIDI note
        self._allocate_drum_voices()

    def _allocate_drum_voices(self):
        """Pre-allocate one synth voice per drum (voices 0-7 reserved for drums)."""
        for drum_idx in range(8):
            self.drum_voices[drum_idx] = {
                "drum_idx": drum_idx,
                "voice_idx": drum_idx,  # Voice 0-7 are reserved for drums
                "last_note": None,  # Track last triggered note for cleanup
                "is_active": False,
            }

            # Initialize parameters for each drum's MIDI note to prevent cross-contamination
            drum_name = self._get_drum_name_by_index(drum_idx)
            drum_preset = DRUM_PRESETS.get(drum_name)
            if drum_preset:
                midi_note = drum_preset.get("midi_note", 36 + drum_idx)
                synth_params = drum_preset.get("synth_params", {})
                self.midi_note_params[midi_note] = synth_params.copy()

    def trigger_drum(self, drum_idx: int, velocity: int, humanize_velocity: float = 1.0):
        """
        Trigger a drum hit with a specific velocity.

        This method:
        1. Caches drum-specific synth parameters by MIDI note to prevent parameter overwriting
        2. Applies parameters to synth engine right before note_on for correct voice application
        3. Ensures monophonic retriggering (same MIDI note)
        4. Triggers the new note with velocity modulation

        Key design: Each drum has a unique MIDI note (Kick=36, Snare=38, etc.), so applying
        parameters immediately before note_on ensures the correct drum parameters are used
        without conflicts between simultaneous drum triggers.

        Args:
            drum_idx: Drum index (0-7)
            velocity: MIDI velocity (0-127)
            humanize_velocity: Velocity modulation from humanization (0.8-1.2 typical)
        """
        if drum_idx < 0 or drum_idx >= 8:
            return

        voice_info = self.drum_voices[drum_idx]
        drum_idx_name = self._get_drum_name_by_index(drum_idx)

        # Get drum preset
        drum_preset = DRUM_PRESETS.get(drum_idx_name)
        if not drum_preset:
            return

        midi_note = drum_preset.get("midi_note", 36 + drum_idx)
        synth_params = drum_preset.get("synth_params", {})

        # Cache parameters for this MIDI note (per-note parameter tracking)
        # This prevents parameter overwriting when multiple drums trigger on same step
        self.midi_note_params[midi_note] = synth_params.copy()

        # Apply drum-specific synthesis parameters immediately before note_on
        # This ensures parameters are set correctly for this specific drum voice
        # before the note triggers, preventing parameter conflicts between drums
        self._apply_drum_parameters(synth_params)

        # Apply humanization to velocity (±20% variation)
        humanized_velocity = max(1, min(127, int(velocity * humanize_velocity)))

        # Trigger the note - the SynthEngine will:
        # - Retrigger if same MIDI note is already playing (no glitch)
        # - Allocate a new voice if available
        # - Voice steal if necessary
        # - Use the parameters we just applied above
        self.synth_engine.note_on(midi_note, humanized_velocity)

        # Track this note as the last triggered note for this drum
        voice_info["last_note"] = midi_note
        voice_info["is_active"] = True

    def release_drum(self, drum_idx: int, velocity: int = 0):
        """
        Release a drum note (allows envelope release phase to complete).

        Args:
            drum_idx: Drum index (0-7)
            velocity: Release velocity (typically 0, affects release curve)
        """
        if drum_idx < 0 or drum_idx >= 8:
            return

        voice_info = self.drum_voices[drum_idx]
        if voice_info["last_note"] is not None:
            self.synth_engine.note_off(voice_info["last_note"], velocity)
            voice_info["is_active"] = False

    def _apply_drum_parameters(self, synth_params: Dict[str, Any]):
        """
        Apply drum-specific parameters to the synthesizer engine.

        Parameters are mapped from drum preset format to SynthEngine format:
        - attack, decay, sustain, release: envelope times (seconds)
        - cutoff_freq → cutoff: filter cutoff frequency
        - oscillator_type → waveform: waveform selection
        - volume → amp_level: output level

        Args:
            synth_params: Dict of drum synthesis parameters from DRUM_PRESETS
        """
        params_to_apply = {}

        # Envelope parameters
        if "attack" in synth_params:
            params_to_apply["attack"] = synth_params["attack"]
        if "decay" in synth_params:
            params_to_apply["decay"] = synth_params["decay"]
        if "sustain" in synth_params:
            params_to_apply["sustain"] = synth_params["sustain"]
        if "release" in synth_params:
            params_to_apply["release"] = synth_params["release"]

        # Filter parameters
        if "cutoff_freq" in synth_params:
            params_to_apply["cutoff"] = synth_params["cutoff_freq"]
        if "resonance" in synth_params:
            params_to_apply["resonance"] = synth_params["resonance"]

        # Oscillator/waveform
        if "oscillator_type" in synth_params:
            # Map drum oscillator types to synth engine waveform names
            osc_type = synth_params["oscillator_type"]
            if osc_type == "noise_white":
                params_to_apply["waveform"] = "noise_white"
            elif osc_type == "noise_pink":
                params_to_apply["waveform"] = "noise_pink"
            elif osc_type in ["sine", "square", "triangle", "sawtooth", "pure_sine"]:
                params_to_apply["waveform"] = osc_type
            else:
                params_to_apply["waveform"] = "sine"

        # Volume
        if "volume" in synth_params:
            params_to_apply["amp_level"] = synth_params["volume"]

        # Apply all parameters at once
        if params_to_apply:
            self.synth_engine.update_parameters(**params_to_apply)

    def _get_drum_name_by_index(self, drum_idx: int) -> str:
        """
        Map drum index (0-7) to drum name from DRUM_PRESETS.

        Args:
            drum_idx: Drum index (0-7)

        Returns:
            Drum name (e.g., "Kick", "Snare", "Closed HH")
        """
        drum_names = [
            "Kick", "Snare", "Closed HH", "Open HH",
            "Clap", "Tom Hi", "Tom Mid", "Tom Low"
        ]
        if 0 <= drum_idx < len(drum_names):
            return drum_names[drum_idx]
        return "Kick"  # Default fallback

    def all_notes_off(self):
        """Silence all active drums immediately."""
        self.synth_engine.all_notes_off()
        for voice_info in self.drum_voices.values():
            voice_info["last_note"] = None
            voice_info["is_active"] = False

    def get_drum_parameters(self, drum_idx: int) -> Dict[str, Any]:
        """
        Get current parameters for a drum.

        Args:
            drum_idx: Drum index (0-7)

        Returns:
            Dict of drum parameters from DRUM_PRESETS
        """
        drum_name = self._get_drum_name_by_index(drum_idx)
        drum_preset = DRUM_PRESETS.get(drum_name, {})
        return drum_preset.get("synth_params", {})

    def set_drum_parameter(self, drum_idx: int, param_name: str, value: Any):
        """
        Modify a specific parameter for a drum.

        This updates the corresponding preset so future hits use the new value.

        Args:
            drum_idx: Drum index (0-7)
            param_name: Parameter name (e.g., "attack", "decay", "cutoff_freq")
            value: New value for the parameter
        """
        drum_name = self._get_drum_name_by_index(drum_idx)
        drum_preset = DRUM_PRESETS.get(drum_name)
        if drum_preset and "synth_params" in drum_preset:
            drum_preset["synth_params"][param_name] = value
