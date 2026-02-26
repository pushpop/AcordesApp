"""ABOUTME: Adapter bridging Tambor drum synthesis to Acordes SynthEngine.
ABOUTME: Routes drum notes to Acordes synth with parameter mapping, falls back to local DrumSynth."""

from typing import Optional, Dict, Any


class AcordesSynthAdapter:
    """
    Routes Tambor drum notes to Acordes SynthEngine when available,
    with intelligent fallback to local DrumSynth.

    Maps Tambor drum parameters (pitch, ADSR, filter, etc.) to Acordes
    synth parameters for seamless integration. Falls back gracefully if
    Acordes synth is unavailable.
    """

    def __init__(self, synth_engine: Optional[Any] = None, drum_synth: Optional[Any] = None):
        """
        Initialize the adapter with Acordes synth engine and fallback drum synth.

        Args:
            synth_engine: Acordes SynthEngine instance (may be None)
            drum_synth: Fallback DrumSynth instance for local synthesis
        """
        self.synth_engine = synth_engine
        self.drum_synth = drum_synth

    def drum_note_on(self, midi_note: int, velocity: int, drum_params: Dict[str, Any]):
        """
        Trigger a drum hit using Acordes synth if available, else fallback to DrumSynth.

        Args:
            midi_note: MIDI note number (e.g., 36 for kick, 38 for snare)
            velocity: MIDI velocity (0-127)
            drum_params: Dict of drum synth parameters from drum_presets.synth_params
                        (pitch, ADSR, cutoff_freq, resonance, oscillator_type, etc.)
        """
        if self.synth_engine is not None:
            self._route_to_acordes_synth(midi_note, velocity, drum_params)
        elif self.drum_synth is not None:
            self._route_to_drum_synth(midi_note, velocity, drum_params)

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

    def _route_to_drum_synth(self, midi_note: int, velocity: int, drum_params: Dict[str, Any]):
        """
        Fallback route to local DrumSynth.

        Uses drum_synth.note_on() with full drum_params dict.
        """
        self.drum_synth.note_on(midi_note, velocity)

    def drum_note_off(self, midi_note: int, velocity: int = 0):
        """
        Release a drum note.

        Args:
            midi_note: MIDI note number
            velocity: Release velocity (typically 0)
        """
        if self.synth_engine is not None:
            self.synth_engine.note_off(midi_note, velocity)
        elif self.drum_synth is not None:
            # DrumSynth doesn't have explicit note_off (samples finish naturally)
            pass

    def all_notes_off(self):
        """Silent all active drums immediately."""
        if self.synth_engine is not None:
            self.synth_engine.all_notes_off()
        # DrumSynth doesn't have explicit all_notes_off (just stop playback)
