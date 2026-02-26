"""ABOUTME: Drum synthesizer producing audio from drum preset parameters.
ABOUTME: Uses numpy/scipy for waveform generation and pygame for playback."""

import numpy as np
import threading
from typing import Dict, Optional


SAMPLE_RATE = 48000  # Match common audio interface standard (48kHz)


def _soft_clip(signal: np.ndarray) -> np.ndarray:
    """Apply soft clipping to prevent harsh distortion from multiple drum mixes."""
    # Tanh soft clipping - smooth and musical
    return np.tanh(signal)


def _apply_envelope(signal: np.ndarray, attack: float, decay: float,
                    sustain: float, release: float, total_duration: float) -> np.ndarray:
    """Apply an ADSR envelope to a signal with smooth curves to reduce clicks."""
    n = len(signal)
    env = np.ones(n)

    attack_samples = int(attack * SAMPLE_RATE)
    decay_samples = int(decay * SAMPLE_RATE)
    release_samples = int(release * SAMPLE_RATE)
    sustain_end = n - release_samples

    # Attack - use exponential curve for smoother onset
    if attack_samples > 0:
        end = min(attack_samples, n)
        # Exponential attack curve: faster initially, then levels off
        t = np.linspace(0, 1, end)
        env[:end] = 1.0 - np.exp(-5.0 * t)

    # Decay to sustain level - exponential decay
    decay_start = attack_samples
    decay_end = min(decay_start + decay_samples, n)
    if decay_end > decay_start:
        t = np.linspace(0, 1, decay_end - decay_start)
        env[decay_start:decay_end] = 1.0 - (1.0 - sustain) * (1.0 - np.exp(-3.0 * t))

    # Sustain
    if sustain_end > decay_end:
        env[decay_end:sustain_end] = sustain

    # Release - exponential release curve
    if release_samples > 0 and sustain_end < n:
        t = np.linspace(0, 1, n - sustain_end)
        env[sustain_end:] = sustain * np.exp(-5.0 * t)

    return signal * env


def _lowpass_filter(signal: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Simple one-pole low-pass filter."""
    rc = 1.0 / (2.0 * np.pi * cutoff_hz)
    dt = 1.0 / SAMPLE_RATE
    alpha = dt / (rc + dt)

    filtered = np.zeros_like(signal)
    filtered[0] = signal[0]
    for i in range(1, len(signal)):
        filtered[i] = filtered[i - 1] + alpha * (signal[i] - filtered[i - 1])
    return filtered


def _synthesize_drum(params: dict, duration: float) -> np.ndarray:
    """Synthesize a drum hit from preset parameters."""
    n = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n, endpoint=False)

    # Apply tune parameter (in semitones) to frequency
    # Semitone formula: new_freq = original_freq * 2^(semitones/12)
    tune_semitones = params.get("tune", 0)
    tune_factor = 2.0 ** (tune_semitones / 12.0)

    osc_type = params.get("oscillator_type", "sine")

    if osc_type == "sine":
        # Pitch-swept sine for kick/tom feel
        freq_start = params.get("pitch_start", 200.0) * tune_factor
        freq_end = params.get("pitch_end", 50.0) * tune_factor
        freq = np.linspace(freq_start, freq_end, n)
        phase = np.cumsum(2.0 * np.pi * freq / SAMPLE_RATE)
        signal = np.sin(phase)

    elif osc_type == "noise":
        signal = np.random.uniform(-1.0, 1.0, n)

    elif osc_type == "sine+noise":
        # Mixed: tonal body + noise transient
        freq = params.get("pitch_start", 200.0) * tune_factor
        tone = np.sin(2.0 * np.pi * freq * t)
        noise = np.random.uniform(-1.0, 1.0, n)
        mix = params.get("noise_mix", 0.5)
        signal = (1.0 - mix) * tone + mix * noise

    else:
        signal = np.zeros(n)

    # Apply ADSR envelope
    signal = _apply_envelope(
        signal,
        attack=params.get("attack", 0.001),
        decay=params.get("decay", 0.1),
        sustain=params.get("sustain", 0.0),
        release=params.get("release", 0.05),
        total_duration=duration,
    )

    # Apply low-pass filter
    cutoff = params.get("cutoff_freq", 8000.0)
    if cutoff < SAMPLE_RATE / 2:
        signal = _lowpass_filter(signal, cutoff)

    # Apply volume (reduce slightly to allow headroom for multiple drums)
    signal *= params.get("volume", 0.8) * 0.8

    # Apply soft clipping instead of hard clipping for better blending of multiple drums
    signal = _soft_clip(signal)

    return signal


class DrumSynth:
    """
    Drum synthesizer using scipy/numpy for waveform generation
    and pygame for audio playback.
    """

    def __init__(self, force_preload_all: bool = False):
        self._pygame_ready = False
        self._sound_cache: Dict[int, object] = {}
        self._lock = threading.Lock()
        self._init_pygame()

        # Preload all drum sounds at startup if requested (avoids blocking during playback)
        if force_preload_all:
            self._preload_all_drums()

    def _init_pygame(self):
        """Initialize pygame mixer for audio playback."""
        try:
            import pygame
            pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
            pygame.mixer.init()
            self._pygame = pygame
            self._pygame_ready = True
        except Exception as e:
            print(f"[DrumSynth] pygame init failed: {e}")
            self._pygame_ready = False

    def _preload_all_drums(self):
        """Preload all drum sounds in background thread to avoid blocking during playback."""
        if not self._pygame_ready:
            return

        def _preload_bg():
            """Background thread function to preload all drums."""
            try:
                from music.drum_presets import DRUM_PRESETS

                for drum_name, drum_config in DRUM_PRESETS.items():
                    midi_note = drum_config.get("midi_note")
                    synth_params = drum_config.get("synth_params", {})

                    if midi_note is not None:
                        self.preload(midi_note, synth_params)

            except Exception as e:
                print(f"[DrumSynth] Error preloading drums: {e}")

        # Run preload in background daemon thread (won't block startup)
        preload_thread = threading.Thread(target=_preload_bg, daemon=True)
        preload_thread.start()

    def preload(self, midi_note: int, synth_params: dict):
        """Pre-render a drum sound and cache it."""
        if not self._pygame_ready:
            return
        duration = synth_params.get("decay", 0.2) + synth_params.get("release", 0.1) + 0.05
        duration = min(duration, 1.5)  # Cap at 1.5 seconds

        samples = _synthesize_drum(synth_params, duration)
        pcm_mono = (samples * 32767).astype(np.int16)

        # pygame mixer uses stereo — duplicate mono channel
        pcm_stereo = np.column_stack((pcm_mono, pcm_mono))

        sound = self._pygame.sndarray.make_sound(pcm_stereo)
        with self._lock:
            self._sound_cache[midi_note] = sound

    def note_on(self, midi_note: int, velocity: int = 100):
        """Play a cached drum sound."""
        if not self._pygame_ready:
            return
        with self._lock:
            sound = self._sound_cache.get(midi_note)
        if sound is not None:
            volume = min(1.0, velocity / 127.0)
            sound.set_volume(volume)
            sound.play()

    def note_off(self, midi_note: int, velocity: int = 0):
        """No-op: drum sounds are one-shot, they decay naturally."""
        pass

    def all_notes_off(self):
        """Stop all currently playing sounds."""
        if self._pygame_ready:
            self._pygame.mixer.stop()

    def is_ready(self) -> bool:
        """Return True if audio is available."""
        return self._pygame_ready
