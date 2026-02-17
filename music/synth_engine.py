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

    def __init__(self, sample_rate: int, voice_index: int = 0):
        """Initialize a voice.

        Args:
            sample_rate: Audio sample rate
            voice_index: Voice number (0-3 for 4-voice poly) - used for phase offset
        """
        self.sample_rate = sample_rate
        self.voice_index = voice_index
        self.midi_note: Optional[int] = None
        self.base_frequency: Optional[float] = None  # Base frequency (before pitch bend)
        self.frequency: Optional[float] = None  # Actual frequency (with pitch bend applied)
        self.phase = 0.0
        self.envelope_time = 0.0
        self.note_active = False
        self.is_releasing = False
        self.release_start_level = 0.0
        self.steal_start_level = 0.0  # For smooth voice stealing crossfade
        self.age = 0.0  # Track how long the voice has been playing
        self.filter_state = 0.0  # Per-voice filter state
        self.velocity = 1.0  # MIDI velocity (0.0 to 1.0)
        self.dc_blocker_x = 0.0  # DC blocker previous input
        self.dc_blocker_y = 0.0  # DC blocker previous output

        # Phase offset for polyphonic spread (Yamaha CS-80 style)
        # Each voice gets a small fixed phase offset for richer polyphony
        # This prevents phase cancellation when multiple notes play
        self.phase_offset = (voice_index * np.pi / 4.0) % (2 * np.pi)  # 0°, 45°, 90°, 135°

        # Stereo pan position for this voice (fixed per voice)
        # 16 voices distributed evenly across stereo field (0.0=left, 1.0=right)
        # Symmetrical around center (0.5) for balanced stereo image
        # Pattern: Alternates L-R to spread consecutive notes across field
        pan_positions = [
            0.20, 0.80,  # Voices 0-1:  Wide L-R
            0.30, 0.70,  # Voices 2-3:  Mid-wide L-R
            0.35, 0.65,  # Voices 4-5:  Medium L-R
            0.40, 0.60,  # Voices 6-7:  Inner L-R
            0.42, 0.58,  # Voices 8-9:  Close L-R
            0.45, 0.55,  # Voices 10-11: Near center
            0.47, 0.53,  # Voices 12-13: Very close center
            0.49, 0.51   # Voices 14-15: Almost center
        ]
        self.pan = pan_positions[voice_index] if voice_index < len(pan_positions) else 0.5

    def is_available(self) -> bool:
        """Check if this voice is available for a new note."""
        return not self.note_active and not self.is_releasing

    def is_playing(self, midi_note: int) -> bool:
        """Check if this voice is playing a specific note."""
        return self.midi_note == midi_note and (self.note_active or self.is_releasing)

    def trigger(self, midi_note: int, frequency: float, velocity: float = 1.0):
        """Trigger a new note on this voice with velocity.

        Uses SOFT SYNC (phase reset to zero) for click-free note starts.
        Most digital synths (Yamaha CS-80, Roland Juno, Korg) reset phase
        on note trigger to ensure consistent, click-free sound.
        """
        # Check if voice was previously silent (completely off)
        was_silent = not self.note_active and not self.is_releasing

        # If voice stealing, capture ACTUAL current envelope level for crossfade
        if not was_silent:
            # Voice is being stolen - capture real envelope level
            # This ensures smooth crossfade regardless of where voice was in its cycle
            if self.is_releasing:
                # Calculate actual release level
                progress = self.envelope_time / 0.1  # Assume 100ms release average
                self.steal_start_level = self.release_start_level * max(0.0, 1.0 - progress)
            else:
                # Voice is active - estimate from envelope phase
                # This is approximate but better than fixed 0.5
                if self.envelope_time < 0.01:  # In attack (assume 10ms)
                    self.steal_start_level = self.envelope_time / 0.01 * 0.8
                else:
                    self.steal_start_level = 0.6  # Likely in sustain
        else:
            self.steal_start_level = 0.0  # Starting from silence

        self.midi_note = midi_note
        self.base_frequency = frequency  # Store base frequency
        self.frequency = frequency  # Will be modulated by pitch bend
        self.velocity = velocity
        self.note_active = True
        self.is_releasing = False
        self.envelope_time = 0.0
        self.age = 0.0  # Reset age when triggered

        # PHASE SYNC: All voices sync to zero on trigger
        # This ensures ALL voices start at the same point in their cycle
        # For phase coherent polyphony (all notes in-phase)
        self.phase = 0.0

        # CRITICAL: Only reset filter state if voice was completely silent
        # If voice was playing/releasing, preserve filter state to prevent clicks
        # This is how polyphonic synths avoid clicks during voice stealing
        if was_silent:
            self.filter_state = 0.0
            self.dc_blocker_x = 0.0
            self.dc_blocker_y = 0.0

    def release(self, attack: float, decay: float, sustain: float, intensity: float):
        """Start the release phase for this voice."""
        if self.note_active:
            self.is_releasing = True
            self.note_active = False

            # Capture current envelope level for smooth release (with velocity)
            velocity_scaled_intensity = intensity * self.velocity

            if self.envelope_time < attack:
                # During attack phase
                if attack > 0:
                    self.release_start_level = (self.envelope_time / attack) * velocity_scaled_intensity
                else:
                    self.release_start_level = velocity_scaled_intensity
            elif self.envelope_time < attack + decay:
                # During decay phase
                if decay > 0:
                    decay_progress = (self.envelope_time - attack) / decay
                    self.release_start_level = velocity_scaled_intensity * (1.0 - decay_progress * (1.0 - sustain))
                else:
                    self.release_start_level = velocity_scaled_intensity * sustain
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
        self.buffer_size = 256  # Low latency (~5.3ms) for responsive playing
        self.num_voices = 16  # Modern polyphonic synth standard (matches Access Virus TI, Nord Lead)

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
        self.octave_enabled = True  # Enable/disable octave transpose feature

        # MASTER CLOCK (Yamaha CS-80 style phase-coherent polyphony)
        # All oscillators sync to this master timebase for musically coherent sound
        self.master_phase = 0.0  # Global phase counter that runs continuously
        self.master_phase_inc = 2 * np.pi * 440.0 / self.sample_rate  # Reference: A440

        # ┌─────────────────────────────────────────────────────────┐
        # │ ENVELOPE (ADSR)                                          │
        # └─────────────────────────────────────────────────────────┘
        self.attack = 0.01    # 0.001s to 5.0s (1ms to 5 seconds) - Attack time
        self.decay = 0.2      # 0.001s to 5.0s (1ms to 5 seconds) - Decay time
        self.sustain = 0.7    # 0.0 to 1.0 (0% to 100%) - Sustain level
        self.release = 0.1    # 0.001s to 5.0s (1ms to 5 seconds) - Release time (100ms default for smooth note-offs)
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
        self.amp_level_target = 0.75  # Target amp level for smoothing
        self.amp_level_current = 0.75  # Current smoothed amp level
        self.amp_smoothing = 0.95  # Smoothing factor (prevents clicks on amp changes)
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
        # Create voices with unique indices for phase offset diversity
        self.voices: List[Voice] = [Voice(self.sample_rate, i) for i in range(self.num_voices)]

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
                    channels=2,  # Stereo output for richer polyphonic sound
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

    def _poly_blep(self, t: float, dt: float) -> float:
        """PolyBLEP (Polynomial Band-Limited Step) residual for anti-aliasing.

        Eliminates aliasing from discontinuous waveforms by smoothing hard transitions.
        This is essential for digital synthesis to sound like analog hardware.

        Args:
            t: Normalized phase position (0 to 1)
            dt: Phase increment per sample (frequency / sample_rate)

        Returns:
            PolyBLEP correction value
        """
        if t < dt:
            # Rising discontinuity
            t = t / dt
            return t + t - t * t - 1.0
        elif t > 1.0 - dt:
            # Falling discontinuity
            t = (t - 1.0) / dt
            return t * t + t + t + 1.0
        return 0.0

    def _generate_waveform(self, voice: Voice, num_samples: int, master_phase_start: float) -> np.ndarray:
        """Generate waveforms using master-clock synchronized oscillators.

        Yamaha CS-80 inspired: All voices reference a global master clock for
        phase-coherent polyphony. This ensures multiple notes sound musical together.

        Args:
            voice: The voice to generate waveform for
            num_samples: Number of samples to generate
            master_phase_start: Starting master phase for this buffer
        """
        # Apply octave transpose (organ feet: 32', 16', 8', 4', 2') - if enabled
        if voice.frequency is None:
            frequency = 440.0  # Default frequency when idle
        else:
            # Apply octave transpose only if enabled
            if self.octave_enabled and self.octave != 0:
                frequency = voice.frequency * (2.0 ** self.octave)
            else:
                frequency = voice.frequency

        # Calculate phase increment per sample
        phase_inc = 2 * np.pi * frequency / self.sample_rate

        # Pre-allocate output array
        samples = np.zeros(num_samples, dtype=np.float32)

        # MASTER CLOCK SYNCHRONIZATION
        # Each voice maintains its phase relative to when it was triggered,
        # but all voices advance in sync with the master clock
        current_phase = voice.phase

        for i in range(num_samples):
            if self.waveform == "sine":
                # CS-80 STYLE SINE WAVE (Yamaha IG00158 waveshaper emulation)
                # The CS-80 generates sine from sawtooth using analog waveshaper
                # This creates a warmer, slightly imperfect sine with subtle harmonics

                # Generate sawtooth core (like the VCO chip)
                t = (current_phase / (2 * np.pi)) % 1.0
                saw = 2.0 * t - 1.0

                # Waveshaper: Apply polynomial transfer function to convert saw→sine
                # CS-80 uses analog circuit, we approximate with Chebyshev-like polynomial
                # This adds slight harmonic content (warmth) compared to pure sine
                # Formula approximates: sin(x) ≈ x - x³/6 + x⁵/120 (Taylor series)
                x = saw * np.pi  # Scale to ±π range
                # Polynomial waveshaping (approximates sine with slight imperfection)
                sine_shaped = x - (x**3) / 6.0 + (x**5) / 120.0

                # Add tiny bit of the original sawtooth for analog "warmth"
                # Real analog circuits have some feed-through
                samples[i] = sine_shaped * 0.98 + saw * 0.02

            elif self.waveform == "triangle":
                # Triangle wave - continuous formula (no discontinuities)
                t = (current_phase / (2 * np.pi)) % 1.0
                samples[i] = 4.0 * np.abs(t - 0.5) - 1.0

            elif self.waveform == "square":
                # Square wave - simple sign function
                samples[i] = 1.0 if np.sin(current_phase) >= 0 else -1.0

            else:  # sawtooth
                # Sawtooth wave - ascending ramp
                t = (current_phase / (2 * np.pi)) % 1.0
                samples[i] = 2.0 * t - 1.0

            # Increment phase (locked to master clock rate)
            current_phase += phase_inc

            # Keep phase wrapped (prevent overflow)
            if current_phase >= 2 * np.pi:
                current_phase -= 2 * np.pi

        # Store final phase for next buffer
        voice.phase = current_phase

        return samples

    def _apply_envelope(self, voice: Voice, samples: np.ndarray, num_samples: int) -> np.ndarray:
        """Apply ADSR envelope with proper release phase and velocity sensitivity to a voice.

        Optimized using NumPy vectorization for better performance.
        """
        dt = 1.0 / self.sample_rate

        # VELOCITY CURVE (Hardware synth style - Yamaha/Roland standard)
        # Most hardware synths use moderate exponential curve
        # Yamaha DX7: ~1.2-1.4 exponent, Roland: ~1.3 exponent
        # This gives natural dynamic response without over-compression
        VELOCITY_CURVE = 1.3  # Moderate exponential (1.0=linear, 2.0=quadratic)
        VELOCITY_FLOOR = 0.15  # Minimum 15% intensity (even softest note is audible)

        velocity_curved = voice.velocity ** VELOCITY_CURVE
        # Apply velocity floor: even velocity=1 gives 15% intensity
        velocity_scaled = VELOCITY_FLOOR + (1.0 - VELOCITY_FLOOR) * velocity_curved
        velocity_scaled_intensity = self.intensity * velocity_scaled

        # Create time array for this buffer
        times = voice.envelope_time + np.arange(num_samples) * dt

        if voice.is_releasing:
            # Release phase - linear fade to zero with extra tail for click prevention
            release_progress = times / self.release
            envelope = voice.release_start_level * np.maximum(0.0, 1.0 - release_progress)

            # Add a short exponential tail at the very end (last 5ms) to ensure zero crossing
            # This prevents clicks when the envelope reaches its end
            TAIL_TIME = 0.005  # 5ms tail
            tail_mask = (times >= self.release - TAIL_TIME) & (times <= self.release)
            if np.any(tail_mask):
                # Exponential fade in the tail region
                tail_times = times[tail_mask] - (self.release - TAIL_TIME)
                tail_progress = tail_times / TAIL_TIME
                # Exponential curve: e^(-6*t) to smoothly reach zero
                tail_curve = np.exp(-6.0 * tail_progress)
                envelope[tail_mask] *= tail_curve

            # Update timing
            voice.envelope_time = times[-1] + dt
            voice.age += num_samples * dt

            # Check if voice finished releasing
            # Only reset when we're truly at zero to prevent clicks
            if times[-1] >= self.release + TAIL_TIME:
                voice.reset()

        elif voice.note_active:
            # ADSR Envelope - simple linear segments
            envelope = np.zeros(num_samples, dtype=np.float32)

            # Attack phase - linear ramp from 0 to peak
            attack_mask = times < self.attack
            if self.attack > 0:
                envelope[attack_mask] = (times[attack_mask] / self.attack) * velocity_scaled_intensity
            else:
                # Instant attack
                envelope[attack_mask] = velocity_scaled_intensity

            # ANTI-CLICK FADE-IN (velocity-independent)
            # Critical for fast playing - prevents clicks from rapid note triggers
            # Uses aggressive exponential curve for fast fade with smooth onset
            ANTI_CLICK_TIME = 0.002  # 2ms anti-click fade (fast for rapid playing)
            anti_click_mask = times < ANTI_CLICK_TIME
            if np.any(anti_click_mask):
                # Very aggressive exponential: 1 - e^(-10t) for ultra-fast fade
                # Reaches 99.99% in 2ms but starts extremely gently
                fade_progress = times[anti_click_mask] / ANTI_CLICK_TIME
                fade_curve = 1.0 - np.exp(-10.0 * fade_progress)
                # Apply fade to envelope (multiply, don't replace)
                envelope[anti_click_mask] *= fade_curve

            # VOICE STEALING CROSSFADE (click prevention for polyphony)
            # Critical for fast playing - smooth transition when voice is stolen
            STEAL_CROSSFADE_TIME = 0.003  # 3ms crossfade (fast for rapid playing)
            if voice.steal_start_level > 0.001:
                steal_mask = times < STEAL_CROSSFADE_TIME
                if np.any(steal_mask):
                    # Very aggressive exponential crossfade: 1 - e^(-8t)
                    steal_progress = times[steal_mask] / STEAL_CROSSFADE_TIME
                    fade_curve = 1.0 - np.exp(-8.0 * steal_progress)  # Fast exponential
                    envelope[steal_mask] = (
                        voice.steal_start_level * (1.0 - fade_curve) +
                        envelope[steal_mask] * fade_curve
                    )
                    # Clear steal level after crossfade applied
                    if times[-1] >= STEAL_CROSSFADE_TIME:
                        voice.steal_start_level = 0.0

            # Decay phase - linear ramp from peak to sustain
            decay_end = self.attack + self.decay
            decay_mask = (times >= self.attack) & (times < decay_end)
            if self.decay > 0:
                decay_progress = (times[decay_mask] - self.attack) / self.decay
                envelope[decay_mask] = velocity_scaled_intensity * (1.0 - decay_progress * (1.0 - self.sustain))
            else:
                envelope[decay_mask] = velocity_scaled_intensity * self.sustain

            # Sustain phase - constant level
            sustain_mask = times >= decay_end
            envelope[sustain_mask] = velocity_scaled_intensity * self.sustain

            # Update voice timing
            voice.envelope_time = times[-1] + dt
            voice.age += num_samples * dt
        else:
            # Silence
            envelope = np.zeros(num_samples, dtype=np.float32)

        return samples * envelope

    def _apply_filter(self, voice: Voice, samples: np.ndarray) -> np.ndarray:
        """Apply low-pass filter with KEY TRACKING and VELOCITY sensitivity.

        Hardware synth features (Yamaha CS-80, Moog, Roland Juno):
        - Key Tracking: Filter cutoff follows note pitch (higher notes = brighter)
        - Velocity: Harder playing opens filter more (expressive playing)
        """
        # BASE CUTOFF from user control
        base_cutoff = self.cutoff

        # KEY TRACKING (Keyboard Follow)
        # Filter cutoff follows the played note frequency
        # This makes high notes brighter and low notes darker (natural)
        # Amount: 50% tracking (0% = no tracking, 100% = full tracking)
        KEY_TRACKING_AMOUNT = 0.5  # 50% key tracking
        if voice.frequency is not None:
            # Calculate how much to adjust cutoff based on note frequency
            # Reference: A440 (MIDI note 69)
            reference_freq = 440.0
            # Use actual played frequency (with octave transpose if enabled)
            if self.octave_enabled and self.octave != 0:
                freq_with_octave = voice.frequency * (2.0 ** self.octave)
            else:
                freq_with_octave = voice.frequency
            # Multiply cutoff by frequency ratio
            key_tracking_multiplier = 1.0 + KEY_TRACKING_AMOUNT * (freq_with_octave / reference_freq - 1.0)
            base_cutoff = base_cutoff * key_tracking_multiplier

        # VELOCITY SENSITIVITY
        # Harder playing (higher velocity) opens filter more
        # Creates expressive, dynamic timbre control
        # Amount: velocity scales cutoff from 70% to 130%
        VELOCITY_TO_FILTER_AMOUNT = 0.6  # 60% velocity sensitivity
        velocity_multiplier = 0.7 + (voice.velocity * VELOCITY_TO_FILTER_AMOUNT)

        # Final cutoff with key tracking + velocity
        final_cutoff = base_cutoff * velocity_multiplier
        final_cutoff = np.clip(final_cutoff, 20.0, 20000.0)  # Keep in valid range

        # Calculate filter coefficient
        alpha = 2 * np.pi * final_cutoff / self.sample_rate
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

            # Smooth amp level changes to prevent clicks
            if abs(self.amp_level_current - self.amp_level_target) > 0.0001:
                self.amp_level_current = self.amp_level_current * self.amp_smoothing + \
                                        self.amp_level_target * (1.0 - self.amp_smoothing)
            else:
                self.amp_level_current = self.amp_level_target

            # MASTER CLOCK (Yamaha CS-80 style)
            # Advance the global master phase - all voices sync to this
            master_phase_start = self.master_phase
            master_phase_inc = self.master_phase_inc * frame_count
            self.master_phase = (self.master_phase + master_phase_inc) % (2 * np.pi)

            # Mix all active/releasing voices to STEREO
            # Each voice has its own pan position for spatial separation
            mixed_left = np.zeros(frame_count, dtype=np.float32)
            mixed_right = np.zeros(frame_count, dtype=np.float32)
            active_voice_count = 0

            for voice in self.voices:
                # Only process voices that are active or releasing
                if voice.note_active or voice.is_releasing:
                    # CORRECT SIGNAL FLOW (like Yamaha CS-80, Moog, Roland Juno)
                    # OSC → FILTER → VCA(ENV) → DC BLOCKER

                    # 1. OSC: Generate waveform at full amplitude (synchronized to master clock)
                    voice_samples = self._generate_waveform(voice, frame_count, master_phase_start)

                    # 2. FILTER: Shape timbre (processes full-strength signal for proper resonance)
                    voice_samples = self._apply_filter(voice, voice_samples)

                    # 3. VCA: Apply envelope to control amplitude (gates the filtered signal)
                    voice_samples = self._apply_envelope(voice, voice_samples, frame_count)

                    # 4. DC BLOCKER: Remove DC offset (final cleanup after all processing)
                    voice_samples = self._apply_dc_blocker(voice, voice_samples)

                    # STEREO PANNING (constant-power law for smooth imaging)
                    # pan = 0.0 (full left), 0.5 (center), 1.0 (full right)
                    pan_angle = voice.pan * np.pi / 2  # 0 to π/2
                    left_gain = np.cos(pan_angle)      # Constant-power panning
                    right_gain = np.sin(pan_angle)

                    # Mix into stereo outputs
                    mixed_left += voice_samples * left_gain
                    mixed_right += voice_samples * right_gain
                    active_voice_count += 1

            # If no voices are active, return silence
            if active_voice_count == 0:
                silence_stereo = np.zeros(frame_count * 2, dtype=np.int16)
                return (silence_stereo.tobytes(), pyaudio.paContinue)

            # STEREO POLYPHONIC MIXING (Professional synth style)
            # Process left and right channels independently for spatial imaging

            # Apply waveform gain compensation (same for both channels)
            waveform_gain = self._get_waveform_gain_compensation()
            mixed_left = mixed_left * waveform_gain
            mixed_right = mixed_right * waveform_gain

            # Apply master amplitude control (smoothed to prevent clicks)
            mixed_left = mixed_left * self.amp_level_current
            mixed_right = mixed_right * self.amp_level_current

            # Soft saturation/compression for polyphonic mixing
            # This maintains fullness while preventing clipping
            if active_voice_count > 1:
                # Gentle compression for multiple voices
                compression_amount = 0.7 + (0.3 / active_voice_count)
                mixed_left = mixed_left * compression_amount
                mixed_right = mixed_right * compression_amount

            # Final soft clipping using tanh for smooth saturation
            mixed_left = np.tanh(mixed_left * 0.9)
            mixed_right = np.tanh(mixed_right * 0.9)

            # Convert from float32 [-1.0, 1.0] to int16 [-32767, 32767]
            mixed_left = np.clip(mixed_left * 32767.0, -32767, 32767).astype(np.int16)
            mixed_right = np.clip(mixed_right * 32767.0, -32767, 32767).astype(np.int16)

            # Interleave left and right channels for stereo output
            # Format: [L, R, L, R, L, R, ...]
            stereo_output = np.empty(frame_count * 2, dtype=np.int16)
            stereo_output[0::2] = mixed_left   # Even indices = left
            stereo_output[1::2] = mixed_right  # Odd indices = right

            return (stereo_output.tobytes(), pyaudio.paContinue)

        except Exception as e:
            # If anything goes wrong in the callback, return stereo silence to avoid crashes
            print(f"Audio callback error: {e}")
            silence_stereo = np.zeros(frame_count * 2, dtype=np.int16)
            return (silence_stereo.tobytes(), pyaudio.paContinue)

    def note_on(self, midi_note: int, velocity: int = 127):
        """Queue a note on event for processing in the audio callback.

        This ensures MIDI events are synchronized with audio buffer boundaries,
        preventing clicks from mid-buffer note triggers.
        """
        # Convert MIDI velocity (0-127) to normalized float (0.0-1.0)
        # Hardware synths use LINEAR normalization at input
        # Velocity curve is applied later in the envelope/filter stages
        if velocity == 0:
            velocity = 1  # MIDI spec: velocity 0 = note off, treat as minimum
        velocity_normalized = velocity / 127.0  # Linear: 0.008 to 1.0

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

    def update_parameters(self, waveform=None, octave=None, octave_enabled=None, amp_level=None,
                         cutoff=None, resonance=None, attack=None, decay=None, sustain=None,
                         release=None, intensity=None):
        """Update synth parameters."""
        if waveform is not None:
            self.waveform = waveform
        if octave is not None:
            self.octave = octave
        if octave_enabled is not None:
            self.octave_enabled = octave_enabled
        if amp_level is not None:
            # Set target for smoothing (prevents clicks on amp changes)
            self.amp_level_target = amp_level
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

    def warm_up(self):
        """Warm up the audio stream by playing a silent note.
        
        This primes the PyAudio buffers and ensures the callback is running
        smoothly before the user triggers any real notes.
        """
        if not self.is_available():
            return
            
        # Trigger a silent note (velocity 0 handled as minimum audible but effectively silent for warm up)
        # MIDI note 0 is outside common range
        self.note_on(0, 1)
        # Immediately release it
        self.note_off(0)
