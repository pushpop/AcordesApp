"""ABOUTME: Drum preset definitions for Tambor drum machine.
ABOUTME: Maps drum names to MIDI notes and synthesizer parameter configurations."""

# Standard General MIDI drum kit notes (for synth_engine triggering)
DRUM_PRESETS = {
    "Kick": {
        "midi_note": 36,  # Bass Drum 1
        "display_name": "Kick",
        "synth_params": {
            # Oscillator: pink noise + sine sub-bass
            "oscillator_type": "sine",
            "noise_type": "noise_pink",  # Pink noise for sub-bass texture

            # Envelope (ADSR in seconds) - percussive
            "attack": 0.0005,     # Very fast attack (0.5ms)
            "decay": 0.3,         # Main shaper - controls boom vs punch
            "sustain": 0.0,       # No sustain - percussive
            "release": 0.05,      # Short tail (50ms)

            # Filter - shaped for low-end focus
            "cutoff_freq": 400,   # Low-pass filter cutoff (Hz)
            "resonance": 0.3,     # Minimal resonance for clean sound

            # Amplitude
            "volume": 0.95,       # Near full volume for punch
        }
    },

    "Snare": {
        "midi_note": 38,  # Acoustic Snare
        "display_name": "Snare",
        "synth_params": {
            # Oscillator: white noise for crisp attack
            "oscillator_type": "noise_white",

            # Envelope - crisp with medium decay
            "attack": 0.0003,     # Very fast (0.3ms)
            "decay": 0.12,        # Snare decay - controls crispness
            "sustain": 0.0,       # No sustain
            "release": 0.03,      # Quick release

            # Filter - high-pass for presence
            "cutoff_freq": 7000,  # High cutoff for snap
            "resonance": 0.4,     # Adds presence

            # Amplitude
            "volume": 0.85,       # Good punch
        }
    },

    "Closed HH": {
        "midi_note": 42,  # Closed Hi-Hat
        "display_name": "Closed HH",
        "synth_params": {
            # Oscillator: white noise for metallic shimmer
            "oscillator_type": "noise_white",

            # Envelope - very short and tight
            "attack": 0.0002,     # Ultra-fast (0.2ms)
            "decay": 0.07,        # Tight decay for closed feel
            "sustain": 0.0,       # No sustain
            "release": 0.015,     # Very short

            # Filter - high-pass for metallic character
            "cutoff_freq": 10000, # High frequency for brightness
            "resonance": 0.5,     # More resonance = metallic

            # Amplitude
            "volume": 0.75,       # Moderate volume
        }
    },

    "Open HH": {
        "midi_note": 46,  # Open Hi-Hat
        "display_name": "Open HH",
        "synth_params": {
            # Oscillator: white noise for bright, sustained shimmer
            "oscillator_type": "noise_white",

            # Envelope - longer and brighter than closed
            "attack": 0.0002,     # Fast (0.2ms)
            "decay": 0.25,        # Longer decay for open feel
            "sustain": 0.08,      # Small sustain for brightness
            "release": 0.04,      # Moderate release

            # Filter - high-pass for brightness
            "cutoff_freq": 11000, # Very high for shimmer
            "resonance": 0.6,     # Higher resonance for character

            # Amplitude
            "volume": 0.8,        # Bright presence
        }
    },

    "Clap": {
        "midi_note": 39,  # Hand Clap
        "display_name": "Clap",
        "synth_params": {
            # Oscillator: white noise for body
            "oscillator_type": "noise_white",

            # Envelope - slightly delayed attack for realism
            "attack": 0.003,      # Slightly slower (3ms) for clap character
            "decay": 0.1,         # Short-medium decay
            "sustain": 0.0,       # No sustain
            "release": 0.03,      # Quick release

            # Filter - mid-high cutoff for presence
            "cutoff_freq": 6000,  # Mid-high for body
            "resonance": 0.3,     # Moderate resonance

            # Amplitude
            "volume": 0.88,       # Good punch
        }
    },

    "Tom Hi": {
        "midi_note": 50,  # Hi Tom
        "display_name": "Tom Hi",
        "synth_params": {
            # Oscillator: sine wave for pitched drum sound
            "oscillator_type": "sine",
            "pitch_center": 300,  # Center pitch (Hz)

            # Envelope - fast attack with pitch sweep
            "attack": 0.0015,     # Fast (1.5ms)
            "decay": 0.09,        # Tight decay for tom character
            "sustain": 0.0,       # No sustain
            "release": 0.04,      # Short release

            # Filter - open for brightness
            "cutoff_freq": 7000,  # High cutoff for shimmer
            "resonance": 0.3,     # Subtle resonance

            # Amplitude
            "volume": 0.82,       # Good presence
        }
    },

    "Tom Mid": {
        "midi_note": 47,  # Mid Tom
        "display_name": "Tom Mid",
        "synth_params": {
            # Oscillator: sine wave for mid-range tom
            "oscillator_type": "sine",
            "pitch_center": 200,  # Center pitch (Hz)

            # Envelope - percussive with medium decay
            "attack": 0.0015,     # Fast (1.5ms)
            "decay": 0.11,        # Slightly longer than hi-tom
            "sustain": 0.0,       # No sustain
            "release": 0.045,     # Short release

            # Filter - moderate cutoff
            "cutoff_freq": 5500,  # Mid-high cutoff
            "resonance": 0.25,    # Subtle resonance

            # Amplitude
            "volume": 0.82,       # Consistent with hi-tom
        }
    },

    "Tom Low": {
        "midi_note": 43,  # Low Tom
        "display_name": "Tom Low",
        "synth_params": {
            # Oscillator: sine wave for low-range tom
            "oscillator_type": "sine",
            "pitch_center": 120,  # Center pitch (Hz)

            # Envelope - longer decay for low tom warmth
            "attack": 0.002,      # Slightly slower (2ms)
            "decay": 0.14,        # Longest decay of toms
            "sustain": 0.0,       # No sustain
            "release": 0.05,      # Medium release

            # Filter - lower cutoff for warmth
            "cutoff_freq": 3000,  # Lower cutoff
            "resonance": 0.2,     # Subtle resonance

            # Amplitude
            "volume": 0.82,       # Consistent volume
        }
    },
}


def get_preset(drum_name: str) -> dict:
    """Get preset configuration for a drum by name.

    Args:
        drum_name: Name of the drum (e.g., "Kick", "Snare")

    Returns:
        Dictionary containing midi_note and synth_params, or None if not found
    """
    return DRUM_PRESETS.get(drum_name)


def get_all_drum_names() -> list:
    """Get list of all available drum names in order."""
    return list(DRUM_PRESETS.keys())


def get_midi_note(drum_name: str) -> int:
    """Get MIDI note number for a drum."""
    preset = get_preset(drum_name)
    return preset["midi_note"] if preset else None


def get_synth_params(drum_name: str) -> dict:
    """Get synth parameters for a drum."""
    preset = get_preset(drum_name)
    return preset["synth_params"].copy() if preset else None
