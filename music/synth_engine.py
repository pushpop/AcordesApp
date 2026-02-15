"""Synthesizer engine for generating audio waveforms."""
import numpy as np
import threading
import queue
from typing import Optional, List

# Check for PyAudio availability
try:
    import pyaudio
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    pyaudio = None


class Voice:
    """Individual synthesizer voice with its own oscillator and envelope."""

    def __init__(self, sample_rate: int):
        """Initialize a voice."""
        self.sample_rate = sample_rate
        self.midi_note: Optional[int] = None
        self.base_frequency: Optional[float] = None  # Base frequency (before pitch bend)
        self.frequency: Optional[float] = None  # Actual frequency (with pitch bend applied)
        self.phase = 0.0
        self.envelope_time = 0.0
        self.note_active = False
        self.is_releasing = False
        self.release_start_level = 0.0
        self.age = 0.0  # Track how long the voice has been playing
        self.filter_state = 0.0  # Per-voice filter state
        self.velocity = 1.0  # MIDI velocity (0.0 to 1.0)
        self.dc_blocker_x = 0.0  # DC blocker previous input
        self.dc_blocker_y = 0.0  # DC blocker previous output

    def is_available(self) -> bool:
        """Check if this voice is available for a new note."""
        return not self.note_active and not self.is_releasing

    def is_playing(self, midi_note: int) -> bool:
        """Check if this voice is playing a specific note."""
        return self.midi_note == midi_note and (self.note_active or self.is_releasing)

    def trigger(self, midi_note: int, frequency: float, velocity: float = 1.0):
        """Trigger a new note on this voice with velocity."""
        # Check if voice was completely silent before triggering
        was_silent = not self.note_active and not self.is_releasing

        self.midi_note = midi_note
        self.base_frequency = frequency  # Store base frequency
        self.frequency = frequency  # Will be modulated by pitch bend
        self.velocity = velocity
        self.note_active = True
        self.is_releasing = False
        self.envelope_time = 0.0
        self.age = 0.0  # Reset age when triggered

        # Always reset phase to 0 for clean note start
        # This prevents clicks from phase discontinuities
        self.phase = 0.0

        # Only reset filter state if voice was completely silent
        # Preserving filter state reduces clicks when stealing active voices
        if was_silent:
            self.filter_state = 0.0

    def release(self, attack: float, decay: float, sustain: float, intensity: float):
        """Start the release phase for this voice."""
        if self.note_active:
            self.is_releasing = True
            self.note_active = False

            # Capture current envelope level for smooth release (with velocity)
            velocity_scaled_intensity = intensity * self.velocity

            if self.envelope_time < attack:
                # During attack phase
                self.release_start_level = (self.envelope_time / attack) * velocity_scaled_intensity if attack > 0 else velocity_scaled_intensity
            elif self.envelope_time < attack + decay:
                # During decay phase
                decay_progress = (self.envelope_time - attack) / decay if decay > 0 else 1.0
                self.release_start_level = velocity_scaled_intensity * (1.0 - decay_progress * (1.0 - sustain))
            else:
                # During sustain phase
                self.release_start_level = velocity_scaled_intensity * sustain

            self.envelope_time = 0.0

    def reset(self):
        """Reset the voice to silence."""
        self.midi_note = None
        self.base_frequency = None
        self.frequency = None
        self.note_active = False
        self.is_releasing = False
        self.envelope_time = 0.0
        self.age = 0.0
        self.filter_state = 0.0  # Reset filter state
        self.velocity = 1.0  # Reset velocity
        self.dc_blocker_x = 0.0  # Reset DC blocker
        self.dc_blocker_y = 0.0


class SynthEngine:
    """4-voice polyphonic synthesizer engine with oscillator, filter, and envelope."""

    def __init__(self):
        """Initialize the synth engine."""
        self.sample_rate = 48000
        self.buffer_size = 1024  # Optimized for click-free audio (~21.3ms latency)
        self.num_voices = 4

        # Audio output
        self.audio = None
        self.stream = None
        self.running = False

        # ╔═══════════════════════════════════════════════════════════╗
        # ║                    SYNTH PARAMETERS                       ║
        # ╚═══════════════════════════════════════════════════════════╝

        # ┌─────────────────────────────────────────────────────────┐
        # │ OSCILLATOR                                               │
        # └─────────────────────────────────────────────────────────┘
        self.waveform = "sine"  # sine, square, sawtooth, triangle
        self.octave = 0  # Octave transpose: -2, -1, 0, +1, +2 (like 32', 16', 8', 4', 2' organ feet)

        # ┌─────────────────────────────────────────────────────────┐
        # │ ENVELOPE (ADSR)                                          │
        # └─────────────────────────────────────────────────────────┘
        self.attack = 0.01    # 0.001s to 5.0s (1ms to 5 seconds) - Attack time
        self.decay = 0.2      # 0.001s to 5.0s (1ms to 5 seconds) - Decay time
        self.sustain = 0.7    # 0.0 to 1.0 (0% to 100%) - Sustain level
        self.release = 0.05   # 0.001s to 5.0s (1ms to 5 seconds) - Release time
        self.intensity = 0.8  # 0.0 to 1.0 (envelope peak level)

        # ┌─────────────────────────────────────────────────────────┐
        # │ FILTER (Low-Pass with Resonance)                        │
        # └─────────────────────────────────────────────────────────┘
        self.cutoff = 2000.0    # 20Hz to 20000Hz (full audio spectrum)
        self.resonance = 0.3    # 0.0 to 0.9 (0% to 90%, avoid self-oscillation)

        # ┌─────────────────────────────────────────────────────────┐
        # │ AMP (Amplitude/Volume)                                   │
        # └─────────────────────────────────────────────────────────┘
        self.amp_level = 0.75  # 0.0 to 1.0 (0% to 100%) - Master amplitude
        self.amp_compensation = True  # Auto-compensate AMP for waveform differences

        # ┌─────────────────────────────────────────────────────────┐
        # │ MIDI CONTROLLERS                                         │
        # └─────────────────────────────────────────────────────────┘
        self.pitch_bend = 0.0      # -2.0 to +2.0 semitones (MIDI pitch bend)
        self.pitch_bend_target = 0.0  # Target pitch bend for smoothing
        self.pitch_bend_smoothing = 0.85  # Smoothing factor (0.0 = instant, 0.99 = very smooth)
        self.mod_wheel = 0.0       # 0.0 to 1.0 (MIDI CC1 modulation wheel)
        self._pitch_bend_dirty = False  # Flag to track if pitch bend changed

        # Voices (4-voice polyphony)
        self.voices: List[Voice] = [Voice(self.sample_rate) for _ in range(self.num_voices)]

        # Track which MIDI notes are currently held down (for handling voice stealing)
        self.held_notes: set = set()

        # MIDI event queue for synchronization with audio callback
        self.midi_event_queue = queue.Queue()

        # Audio queue
        self.audio_queue = queue.Queue()

        # Initialize audio if available
        if AUDIO_AVAILABLE and pyaudio is not None:
            try:
                self.audio = pyaudio.PyAudio()

                # Find the default output device and use its settings
                default_output = self.audio.get_default_output_device_info()

                self.stream = self.audio.open(
                    format=pyaudio.paInt16,  # 16-bit PCM audio for efficiency
                    channels=1,
                    rate=self.sample_rate,
                    output=True,
                    output_device_index=default_output['index'],
                    frames_per_buffer=self.buffer_size,  # CHUNK size
                    stream_callback=self._audio_callback,
                    # These flags help reduce latency and improve stability
                    start=False  # Don't start immediately
                )

                # Start the stream after initialization
                self.stream.start_stream()
                self.running = True
            except Exception as e:
                print(f"Audio initialization failed: {e}")
                self.running = False

    def _midi_to_frequency(self, midi_note: int) -> float:
        """Convert MIDI note number to frequency in Hz.

        Uses A440 tuning standard (A4 = MIDI note 69 = 440 Hz).
        """
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

    def get_octave_feet_notation(self) -> str:
        """Get organ feet notation for current octave setting.

        Returns:
            Organ feet notation (32', 16', 8', 4', 2', 1')
        """
        feet_map = {
            -2: "32'",  # Two octaves down
            -1: "16'",  # One octave down
            0: "8'",    # Standard pitch (most common)
            1: "4'",    # One octave up
            2: "2'",    # Two octaves up
        }
        return feet_map.get(self.octave, "8'")

    def _get_waveform_gain_compensation(self) -> float:
        """Get gain compensation factor for current waveform.

        Returns equal perceived loudness across all waveforms.
        Sine is the reference (1.4x), other waveforms adjusted accordingly.
        """
        if not self.amp_compensation:
            return 1.0  # No compensation

        # Compensation factors for equal perceived loudness
        compensation_map = {
            "sine": 1.4,      # Boosted for better presence
            "square": 0.8,    # Reduced (square has high RMS)
            "sawtooth": 1.7,  # Boosted to match sine
            "triangle": 1.7,  # Boosted to match sine
        }
        return compensation_map.get(self.waveform, 1.0)

    def _apply_pitch_bend(self, base_frequency: float) -> float:
        """Apply pitch bend to a frequency.

        Args:
            base_frequency: The base frequency before pitch bend

        Returns:
            Frequency with pitch bend applied (±2 semitones range)
        """
        # Pitch bend of ±2 semitones (standard MIDI pitch bend range)
        # pitch_bend is in range -2.0 to +2.0 semitones
        return base_frequency * (2.0 ** (self.pitch_bend / 12.0))

    def _update_voice_frequencies(self):
        """Update all voice frequencies based on current pitch bend with smoothing."""
        # Smooth pitch bend to target value (prevents jumpy behavior)
        if abs(self.pitch_bend - self.pitch_bend_target) > 0.0001:
            self.pitch_bend = self.pitch_bend * self.pitch_bend_smoothing + \
                             self.pitch_bend_target * (1.0 - self.pitch_bend_smoothing)
        else:
            self.pitch_bend = self.pitch_bend_target

        # Update all voice frequencies with smoothed pitch bend
        for voice in self.voices:
            if voice.base_frequency is not None and (voice.note_active or voice.is_releasing):
                voice.frequency = self._apply_pitch_bend(voice.base_frequency)

    def _generate_waveform(self, voice: Voice, num_samples: int) -> np.ndarray:
        """Generate waveform samples for a voice based on current waveform type."""
        if voice.frequency is None:
            return np.zeros(num_samples)

        t = np.arange(num_samples) / self.sample_rate

        # Apply octave transpose (like organ feet: 32', 16', 8', 4', 2')
        # Each octave up/down doubles/halves the frequency
        frequency = voice.frequency * (2.0 ** self.octave)

        if self.waveform == "sine":
            # Sine wave (normalized to -1 to 1)
            samples = np.sin(2 * np.pi * frequency * t + voice.phase)
        elif self.waveform == "square":
            # Square wave (normalized to -1 to 1)
            samples = np.sign(np.sin(2 * np.pi * frequency * t + voice.phase))
        elif self.waveform == "sawtooth":
            # Sawtooth wave (normalized to -1 to 1)
            samples = 2 * ((frequency * t + voice.phase / (2 * np.pi)) % 1) - 1
        else:  # triangle
            # Triangle wave (normalized to -1 to 1)
            samples = 2 * np.abs(2 * ((frequency * t + voice.phase / (2 * np.pi)) % 1) - 1) - 1

        # Update phase for continuity
        voice.phase = (voice.phase + 2 * np.pi * frequency * num_samples / self.sample_rate) % (2 * np.pi)

        return samples

    def _apply_envelope(self, voice: Voice, samples: np.ndarray, num_samples: int) -> np.ndarray:
        """Apply ADSR envelope with proper release phase and velocity sensitivity to a voice.

        Optimized using NumPy vectorization for better performance.
        """
        dt = 1.0 / self.sample_rate
        velocity_scaled_intensity = self.intensity * voice.velocity
        click_prevention_time = 0.002  # 2ms anti-click fade-in (prevents clicks from simultaneous notes)

        # Create time array for this buffer
        times = voice.envelope_time + np.arange(num_samples) * dt

        if voice.is_releasing:
            # Release phase - vectorized linear fade to zero
            release_progress = times / self.release
            envelope = voice.release_start_level * np.maximum(0.0, 1.0 - release_progress)

            # Check if voice finished releasing
            if times[-1] / self.release >= 1.0:
                voice.reset()
            else:
                voice.envelope_time = times[-1] + dt
                voice.age += num_samples * dt

        elif voice.note_active:
            # ADSR Envelope - vectorized computation
            envelope = np.zeros(num_samples, dtype=np.float32)

            # Attack phase
            attack_mask = times < self.attack
            if self.attack > 0:
                envelope[attack_mask] = (times[attack_mask] / self.attack) * velocity_scaled_intensity
            else:
                envelope[attack_mask] = velocity_scaled_intensity

            # Decay phase
            decay_end = self.attack + self.decay
            decay_mask = (times >= self.attack) & (times < decay_end)
            if self.decay > 0:
                decay_progress = (times[decay_mask] - self.attack) / self.decay
                envelope[decay_mask] = velocity_scaled_intensity * (1.0 - decay_progress * (1.0 - self.sustain))
            else:
                envelope[decay_mask] = velocity_scaled_intensity * self.sustain

            # Sustain phase
            sustain_mask = times >= decay_end
            envelope[sustain_mask] = velocity_scaled_intensity * self.sustain

            # Anti-click fade-in (vectorized)
            click_mask = times < click_prevention_time
            if np.any(click_mask):
                envelope[click_mask] *= (times[click_mask] / click_prevention_time)

            # Update voice timing
            voice.envelope_time = times[-1] + dt
            voice.age += num_samples * dt
        else:
            # Silence
            envelope = np.zeros(num_samples, dtype=np.float32)

        return samples * envelope

    def _apply_filter(self, voice: Voice, samples: np.ndarray) -> np.ndarray:
        """Apply simple low-pass filter with per-voice preserved state and resonance.

        Optimized using scipy.signal.lfilter for better performance.
        Falls back to Python loop if scipy not available.
        """
        alpha = 2 * np.pi * self.cutoff / self.sample_rate
        alpha = min(alpha, 1.0)

        # Calculate resonance compensation (boost signal at cutoff frequency)
        # Map resonance (0.0-0.9) to Q factor (0.5-10.0)
        q_factor = 0.5 + (self.resonance * 10.5)  # 0.5 to 11.0
        resonance_gain = 1.0 + (self.resonance * 2.0)  # 1.0 to 3.0 gain boost

        # Try to use scipy for fast IIR filtering
        try:
            from scipy import signal
            # One-pole IIR filter: y[n] = y[n-1] + alpha * (x[n] - y[n-1])
            # Transfer function: H(z) = alpha / (1 - (1-alpha)z^-1)
            b = np.array([alpha], dtype=np.float32)
            a = np.array([1.0, -(1.0 - alpha)], dtype=np.float32)

            # Use lfilter with initial condition to preserve filter state
            filtered, zi = signal.lfilter(b, a, samples, zi=[voice.filter_state])
            voice.filter_state = zi[0]

        except ImportError:
            # Fallback to manual loop if scipy not available
            filtered = np.zeros_like(samples)
            state = voice.filter_state
            for i in range(len(samples)):
                state = state + alpha * (samples[i] - state)
                filtered[i] = state
            voice.filter_state = state

        # Add resonance with proper feedback and peak boost
        if self.resonance > 0.0:
            # Create resonance peak by feeding back the difference between input and output
            # This simulates the resonant peak in analog filters
            resonance_feedback = (samples - filtered) * self.resonance
            filtered = filtered + resonance_feedback

            # Apply gain compensation to make resonance more audible
            filtered = filtered * resonance_gain

        return filtered

    def _apply_dc_blocker(self, voice: Voice, samples: np.ndarray) -> np.ndarray:
        """Apply DC blocking filter to remove DC offset and low-frequency clicks.

        Uses a high-pass filter: y[n] = x[n] - x[n-1] + 0.995 * y[n-1]
        This removes any DC component and very low frequencies that can cause clicks.
        """
        filtered = np.zeros_like(samples)
        x_prev = voice.dc_blocker_x
        y_prev = voice.dc_blocker_y

        for i in range(len(samples)):
            # High-pass filter (DC blocker)
            filtered[i] = samples[i] - x_prev + 0.995 * y_prev
            x_prev = samples[i]
            y_prev = filtered[i]

        # Update voice state
        voice.dc_blocker_x = x_prev
        voice.dc_blocker_y = y_prev

        return filtered

    def _process_midi_events(self):
        """Process all pending MIDI events from the queue.

        This is called at the start of each audio callback to synchronize
        MIDI events with audio buffer boundaries, preventing clicks.
        """
        while not self.midi_event_queue.empty():
            try:
                event = self.midi_event_queue.get_nowait()
                event_type = event['type']

                if event_type == 'note_on':
                    self._trigger_note(event['note'], event['velocity'])
                elif event_type == 'note_off':
                    self._release_note(event['note'])

            except queue.Empty:
                break

    def _trigger_note(self, midi_note: int, velocity_normalized: float):
        """Internal method to trigger a note (called from audio callback)."""
        frequency = self._midi_to_frequency(midi_note)

        # First, check if this note is already playing (retriggering)
        for voice in self.voices:
            if voice.midi_note == midi_note and voice.note_active:
                voice.trigger(midi_note, frequency, velocity_normalized)
                return

        # Find a completely available voice
        for voice in self.voices:
            if voice.is_available():
                voice.trigger(midi_note, frequency, velocity_normalized)
                return

        # No available voice - implement smart voice stealing (optimized)
        best_voice = None
        best_priority = -1
        best_score = -1.0

        for voice in self.voices:
            priority = -1
            score = 0.0

            if (voice.is_releasing and voice.midi_note is not None and
                voice.midi_note not in self.held_notes):
                priority = 2
                score = voice.envelope_time
            elif voice.is_releasing:
                priority = 1
                score = voice.envelope_time
            else:
                priority = 0
                score = voice.age

            if priority > best_priority or (priority == best_priority and score > best_score):
                best_priority = priority
                best_score = score
                best_voice = voice

        if best_voice:
            best_voice.trigger(midi_note, frequency, velocity_normalized)

    def _release_note(self, midi_note: int):
        """Internal method to release a note (called from audio callback)."""
        for voice in self.voices:
            if voice.midi_note == midi_note and voice.note_active:
                voice.release(self.attack, self.decay, self.sustain, self.intensity)

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for PyAudio to generate audio samples from all voices."""
        try:
            # Process all pending MIDI events at the start of the audio buffer
            # This synchronizes MIDI events with audio buffer boundaries
            self._process_midi_events()

            # Always update pitch bend for smooth interpolation
            # (smoothing happens inside _update_voice_frequencies)
            self._update_voice_frequencies()

            # Mix all active voices
            mixed_samples = np.zeros(frame_count, dtype=np.float32)
            active_voice_count = 0

            for voice in self.voices:
                # Only process voices that are active or releasing
                if voice.note_active or voice.is_releasing:
                    # Generate waveform for this voice
                    voice_samples = self._generate_waveform(voice, frame_count)

                    # Apply envelope to this voice
                    voice_samples = self._apply_envelope(voice, voice_samples, frame_count)

                    # Apply filter to this voice (per-voice filtering)
                    voice_samples = self._apply_filter(voice, voice_samples)

                    # Apply DC blocker to remove low-frequency clicks
                    voice_samples = self._apply_dc_blocker(voice, voice_samples)

                    # Mix into the output
                    mixed_samples += voice_samples
                    active_voice_count += 1

            # If no voices are active, return silence
            if active_voice_count == 0:
                return (np.zeros(frame_count, dtype=np.int16).tobytes(), pyaudio.paContinue)

            # Normalize by number of voices to prevent clipping when multiple voices play
            # Use a softer normalization to maintain good volume
            mixed_samples = mixed_samples / np.sqrt(max(active_voice_count, 1))

            # Apply waveform gain compensation for equal perceived loudness
            waveform_gain = self._get_waveform_gain_compensation()
            mixed_samples = mixed_samples * waveform_gain

            # Apply AMP (master amplitude)
            mixed_samples = mixed_samples * self.amp_level

            # Soft clipping using tanh for smoother saturation
            mixed_samples = np.tanh(mixed_samples)

            # Convert from float32 [-1.0, 1.0] to int16 [-32767, 32767]
            # Scale by 32767 and clip to valid range
            mixed_samples = np.clip(mixed_samples * 32767.0, -32767, 32767)

            return (mixed_samples.astype(np.int16).tobytes(), pyaudio.paContinue)

        except Exception as e:
            # If anything goes wrong in the callback, return silence to avoid crashes
            print(f"Audio callback error: {e}")
            return (np.zeros(frame_count, dtype=np.int16).tobytes(), pyaudio.paContinue)

    def note_on(self, midi_note: int, velocity: int = 127):
        """Queue a note on event for processing in the audio callback.

        This ensures MIDI events are synchronized with audio buffer boundaries,
        preventing clicks from mid-buffer note triggers.
        """
        # Convert MIDI velocity (0-127) to normalized float (0.0-1.0)
        # Use a curve to make velocity feel more natural (square root for better response)
        velocity_normalized = np.sqrt(velocity / 127.0)

        # Track this note as held
        self.held_notes.add(midi_note)

        # Queue the event for processing in the audio callback
        self.midi_event_queue.put({
            'type': 'note_on',
            'note': midi_note,
            'velocity': velocity_normalized
        })

    def note_off(self, midi_note: int):
        """Queue a note off event for processing in the audio callback.

        This ensures MIDI events are synchronized with audio buffer boundaries.
        """
        # Remove from held notes
        self.held_notes.discard(midi_note)

        # Queue the event for processing in the audio callback
        self.midi_event_queue.put({
            'type': 'note_off',
            'note': midi_note
        })

    def all_notes_off(self):
        """Emergency: Immediately silence all voices (MIDI panic)."""
        self.held_notes.clear()
        for voice in self.voices:
            # Immediately reset all voices to silence (no release phase)
            voice.reset()

    def pitch_bend_change(self, value: int):
        """Handle MIDI pitch bend change with smoothing.

        Args:
            value: MIDI pitch bend value (0-16383, center = 8192)
        """
        # Convert MIDI pitch bend (0-16383) to semitones (-2 to +2)
        # Center position (8192) = no bend
        normalized = (value - 8192) / 8192.0  # -1.0 to +1.0
        self.pitch_bend_target = normalized * 2.0  # -2.0 to +2.0 semitones
        # Smoothing will happen in _update_voice_frequencies()

    def modulation_change(self, value: int):
        """Handle MIDI modulation wheel change (CC1).

        Args:
            value: MIDI CC value (0-127)
        """
        # Convert MIDI CC (0-127) to normalized (0.0-1.0)
        self.mod_wheel = value / 127.0

    def update_parameters(self, waveform=None, octave=None, amp_level=None, cutoff=None,
                         resonance=None, attack=None, decay=None, sustain=None,
                         release=None, intensity=None):
        """Update synth parameters."""
        if waveform is not None:
            self.waveform = waveform
        if octave is not None:
            self.octave = octave
        if amp_level is not None:
            self.amp_level = amp_level
        if cutoff is not None:
            self.cutoff = cutoff
        if resonance is not None:
            self.resonance = resonance
        if attack is not None:
            self.attack = attack
        if decay is not None:
            self.decay = decay
        if sustain is not None:
            self.sustain = sustain
        if release is not None:
            self.release = release
        if intensity is not None:
            self.intensity = intensity

    def close(self):
        """Clean up audio resources."""
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()

    def is_available(self) -> bool:
        """Check if audio is available."""
        return AUDIO_AVAILABLE and self.running
