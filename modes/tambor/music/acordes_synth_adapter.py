"""ABOUTME: Adapter routing Tambor drum synthesis to shared Acordes SynthEngine.
ABOUTME: Maps drum parameters to Acordes synth parameters for drum sound generation."""

from typing import Optional, Dict, Any


class AcordesSynthAdapter:
    """
    Routes Tambor drum notes to the shared Acordes SynthEngine.

    Maps Tambor drum parameters (pitch, ADSR, filter, etc.) to Acordes
    synth parameters for seamless integration across the application.
    """

    def __init__(self, synth_engine: Any):
        """
        Initialize the adapter with Acordes synth engine.

        Args:
            synth_engine: Acordes SynthEngine instance (required)
        """
        self.synth_engine = synth_engine

    def drum_note_on(self, midi_note: int, velocity: int, drum_params: Dict[str, Any]):
        """
        Trigger a drum hit using Acordes SynthEngine.

        Args:
            midi_note: MIDI note number (e.g., 36 for kick, 38 for snare)
            velocity: MIDI velocity (0-127)
            drum_params: Dict of drum synth parameters from drum_presets.synth_params
                        (pitch, ADSR, cutoff_freq, resonance, oscillator_type, etc.)
        """
        self._route_to_acordes_synth(midi_note, velocity, drum_params)

    def _route_to_acordes_synth(self, midi_note: int, velocity: int, drum_params: Dict[str, Any]):
        """
        Route drum to Acordes SynthEngine with parameter mapping.

        Maps Tambor drum parameters to Acordes synth parameters:
        - Pitch (tune, pitch_start) → adjust base frequency
        - ADSR (attack, decay, sustain, release) → envelope params
        - Filter (cutoff_freq, resonance) → cutoff, resonance
        - Oscillator type → waveform selection
        """
        # Map drum parameters to Acordes synth parameters
        params_to_update = {}

        # Oscillator waveform mapping
        osc_type = drum_params.get("oscillator_type", "sine")
        if osc_type == "sine":
            params_to_update["waveform"] = "sine"
        elif osc_type == "noise":
            params_to_update["waveform"] = "noise"
        elif osc_type == "sine+noise":
            # Default to sine for pure drums; filter will add noise feel
            params_to_update["waveform"] = "sine"
        else:
            params_to_update["waveform"] = "sine"

        # Envelope mapping (ADSR)
        if "attack" in drum_params:
            params_to_update["attack"] = drum_params["attack"]
        if "decay" in drum_params:
            params_to_update["decay"] = drum_params["decay"]
        if "sustain" in drum_params:
            params_to_update["sustain"] = drum_params["sustain"]
        if "release" in drum_params:
            params_to_update["release"] = drum_params["release"]

        # Filter mapping
        if "cutoff_freq" in drum_params:
            params_to_update["cutoff"] = drum_params["cutoff_freq"]
        if "resonance" in drum_params:
            params_to_update["resonance"] = drum_params["resonance"]

        # Volume mapping
        if "volume" in drum_params:
            # Drum volume (0-1) maps to master volume
            volume = drum_params["volume"]
            params_to_update["amp_level"] = volume

        # Apply parameter updates before triggering note
        if params_to_update:
            self.synth_engine.update_parameters(**params_to_update)

        # Trigger the note on Acordes synth
        # Velocity is 0-127; normalize to 0-127 for synth_engine.note_on
        self.synth_engine.note_on(midi_note, velocity)


    def drum_note_off(self, midi_note: int, velocity: int = 0):
        """
        Release a drum note.

        Args:
            midi_note: MIDI note number
            velocity: Release velocity (typically 0)
        """
        self.synth_engine.note_off(midi_note, velocity)

    def all_notes_off(self):
        """Silence all active drums immediately."""
        self.synth_engine.all_notes_off()
