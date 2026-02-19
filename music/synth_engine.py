"""Synthesizer engine for generating audio waveforms."""
import os
import sys
import ctypes
import numpy as np
import threading
import queue
import random as _rnd
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
        self.sample_rate = sample_rate
        self.voice_index = voice_index
        self.midi_note: Optional[int] = None
        self.base_frequency: Optional[float] = None
        self.frequency: Optional[float] = None
        self.phase = 0.0
        self.phase2 = 0.0
        self.envelope_time = 0.0
        self.note_active = False
        self.is_releasing = False
        self.release_start_level = 0.0
        self.steal_start_level = 0.0
        self.age = 0.0
        self.filter_state_lpf1 = 0.0
        self.filter_state_hpf1 = 0.0
        self.filter_state_lpf2 = 0.0
        self.filter_state_hpf2 = 0.0
        # Second-pole states for the resonance cascade (separate from rank 2 oscillator states)
        self.filter_state_lpf1b = 0.0
        self.filter_state_lpf2b = 0.0
        self.velocity = 1.0
        self.release_velocity = 0.5
        self.dc_blocker_x = 0.0
        self.dc_blocker_y = 0.0
        self.last_envelope_level = 0.0
        # Counts samples rendered since the last trigger() call.
        # Used to apply a short fade-in ramp that suppresses the DC-blocker
        # startup transient on fresh note onsets.
        self.onset_samples = 0

        # Phase offset for polyphonic spread
        self.phase_offset = (voice_index * np.pi / 4.0) % (2 * np.pi)
        # Stereo spread table — voices allocated in ascending order (0, 1, 2 …).
        # Voice 0 is always the first triggered for any single note, so it must sit
        # dead-centre (pan=0.5) to produce equal L/R output.  Subsequent voices spread
        # outward in symmetric pairs so the full-polyphony image stays balanced.
        # pan=0.5 → ang=π/4 → cos=sin=0.707 → equal power L and R (correct centre).
        # Layout: 0=C, 1=C, 2=slight-L, 3=slight-R, 4=mid-L, 5=mid-R, 6=wide-L, 7=wide-R
        _pan_table = [0.5, 0.5, 0.44, 0.56, 0.38, 0.62, 0.32, 0.68]
        self.pan = _pan_table[voice_index] if voice_index < len(_pan_table) else 0.5
        # Dedicated phase accumulator for the sine-reinforcement sub-oscillator
        self.sine_phase = 0.0

        # Ladder filter states — 4 integrator stages per rank
        self.filter_state_ladder1: list = [0.0, 0.0, 0.0, 0.0]  # rank 1
        self.filter_state_ladder2: list = [0.0, 0.0, 0.0, 0.0]  # rank 2
        # SVF filter states — lp and bp integrators per rank
        self.filter_state_svf1_lp: float = 0.0
        self.filter_state_svf1_bp: float = 0.0
        self.filter_state_svf2_lp: float = 0.0
        self.filter_state_svf2_bp: float = 0.0

        # Frequency-adaptive onset window (ms) set at trigger time by _trigger_note.
        # Controls both the ONSET_RAMP fade-in (applied before the DC blocker) and
        # the ANTI_I envelope softening window.  Default 3ms covers all mid/high
        # notes; _trigger_note scales this up to 30ms for very low fundamentals so
        # the DC blocker's settling transient is hidden under the onset ramp.
        self.onset_ms: float = 3.0

    def is_available(self) -> bool:
        return not self.note_active and not self.is_releasing

    def is_playing(self, midi_note: int) -> bool:
        return self.midi_note == midi_note and (self.note_active or self.is_releasing)

    def trigger(self, midi_note: int, frequency: float, velocity: float = 1.0):
        """Trigger a new note. Keeps oscillators free-running to prevent phase-jump clicks."""
        was_silent = not self.note_active and not self.is_releasing
        self.steal_start_level = self.last_envelope_level if not was_silent else 0.0

        self.midi_note = midi_note
        self.base_frequency = frequency
        self.frequency = frequency
        self.velocity = velocity
        self.note_active = True
        self.is_releasing = False
        self.envelope_time = 0.0
        self.age = 0.0
        self.onset_samples = 0   # restart the per-voice fade-in ramp
        self.onset_ms = 3.0      # reset to default; _trigger_note sets the real value

        # RESET filter/DC memory if starting from silence OR if this is a voice steal
        # (same voice being retaken by a different note). Preserving stale filter/DC
        # state from the stolen note would cause a DC sag at the start of the new note.
        if True:  # always reset — free-running phase is preserved, states are not
            self.filter_state_lpf1 = self.filter_state_hpf1 = 0.0
            self.filter_state_lpf2 = self.filter_state_hpf2 = 0.0
            self.filter_state_lpf1b = self.filter_state_lpf2b = 0.0
            self.filter_state_ladder1 = [0.0, 0.0, 0.0, 0.0]
            self.filter_state_ladder2 = [0.0, 0.0, 0.0, 0.0]
            self.filter_state_svf1_lp = self.filter_state_svf1_bp = 0.0
            self.filter_state_svf2_lp = self.filter_state_svf2_bp = 0.0
            self.dc_blocker_x = self.dc_blocker_y = 0.0
            # Note: self.phase and self.sine_phase are NOT reset here (Free-Running)

    def release(self, attack: float, decay: float, sustain: float, intensity: float, release_velocity: float = 0.5):
        if self.note_active:
            self.is_releasing = True
            self.note_active = False
            self.release_velocity = release_velocity
            VEL_C, VEL_F = 1.3, 0.15
            v_scaled = VEL_F + (1.0 - VEL_F) * (self.velocity ** VEL_C)
            v_int = intensity * v_scaled
            self.release_start_level = self.last_envelope_level if self.last_envelope_level > 0.0001 else (v_int * sustain)
            self.envelope_time = 0.0

    def reset(self):
        self.midi_note = None
        self.base_frequency = None
        self.frequency = None
        self.note_active = False
        self.is_releasing = False
        self.envelope_time = 0.0
        self.age = 0.0
        self.filter_state_lpf1 = self.filter_state_hpf1 = 0.0
        self.filter_state_lpf2 = self.filter_state_hpf2 = 0.0
        self.filter_state_lpf1b = self.filter_state_lpf2b = 0.0
        self.filter_state_ladder1 = [0.0, 0.0, 0.0, 0.0]
        self.filter_state_ladder2 = [0.0, 0.0, 0.0, 0.0]
        self.filter_state_svf1_lp = self.filter_state_svf1_bp = 0.0
        self.filter_state_svf2_lp = self.filter_state_svf2_bp = 0.0
        self.dc_blocker_x = self.dc_blocker_y = 0.0
        self.last_envelope_level = 0.0
        self.sine_phase = 0.0
        self.onset_samples = 0


class SynthEngine:
    """8-voice polyphonic synthesizer engine with stabilized gain and master volume."""

    def __init__(self):
        self.sample_rate = 48000
        self.buffer_size = 256
        self.num_voices = 8
        self.audio = None
        self.stream = None
        self.running = False

        self.waveform = "sine"
        self.octave = 0
        self.octave_enabled = True
        self.rank2_enabled = False
        self.rank2_waveform = "sawtooth"
        self.rank2_detune = 5.0
        self.rank2_mix = 0.5
        self.sine_mix = 0.0

        self.master_phase = 0.0
        self.master_phase_inc = 2 * np.pi * 440.0 / self.sample_rate

        self.attack = 0.01
        self.decay = 0.2
        self.sustain = 0.7
        self.release = 0.1
        self.intensity = 0.8

        self.cutoff = 2000.0
        self.hpf_cutoff = 20.0
        self.resonance = 0.3
        self.filter_mode = "ladder"   # "ladder" | "svf"

        self.lfo_freq = 1.0
        self.lfo_vco_mod = 0.0
        self.lfo_vcf_mod = 0.0
        self.lfo_vca_mod = 0.0
        self.lfo_phase = 0.0
        # LFO extended — shape + target routing + master depth
        self.lfo_shape  = "sine"   # "sine" | "triangle" | "square" | "sample_hold"
        self.lfo_target = "all"    # "vco"  | "vcf"       | "vca"    | "all"
        self.lfo_depth  = 0.0      # 0.0–1.0 master depth
        self._lfo_sh_value = 0.0   # S&H: current held random value

        # ── FX Delay (stereo ring buffer, max 2 s) ───────────────────────
        self.delay_time     = 0.25   # seconds
        self.delay_feedback = 0.3    # 0.0–0.9
        self.delay_mix      = 0.0    # 0.0–1.0 wet/dry (0 = bypass)
        _dly_len = int(self.sample_rate * 2.0) + 1
        self._delay_buf_l   = np.zeros(_dly_len, dtype=np.float32)
        self._delay_buf_r   = np.zeros(_dly_len, dtype=np.float32)
        self._delay_write   = 0
        self._delay_samples = int(self.delay_time * self.sample_rate)

        # ── Chorus (BBD-style, single shared ring, 4 tap phases) ────────
        self.chorus_rate   = 0.5    # Hz, 0.1–10.0
        self.chorus_depth  = 0.0    # 0.0–1.0 → 0–25ms sweep (0 = bypass)
        self.chorus_mix    = 0.0    # 0.0–1.0 wet/dry (0 = bypass)
        self.chorus_voices = 2      # 1–4 modulated taps
        _cho_len = int(self.sample_rate * 0.030) + 2   # 30ms + guard
        self._chorus_buf_l  = np.zeros(_cho_len, dtype=np.float32)
        self._chorus_buf_r  = np.zeros(_cho_len, dtype=np.float32)
        # Four LFO phases spread 90° apart for natural voice spread
        self._chorus_phases = [i * (np.pi / 2.0) for i in range(4)]
        self._chorus_write  = 0

        # ── Arpeggiator (audio-callback driven clock) ────────────────────
        self.arp_enabled  = False
        self.arp_mode     = "up"    # "up" | "down" | "up_down" | "random"
        self.arp_bpm      = 120.0
        self.arp_gate     = 0.5     # 0.05–1.0 note-on fraction of step
        self.arp_range    = 1       # 1–4 octave span
        # Sequencer state — audio-thread only, no lock needed
        self._arp_held_notes:     list          = []
        self._arp_sequence:       list          = []
        self._arp_index:          int           = 0
        self._arp_step_samples:   int           = int(60.0 / 120.0 * self.sample_rate)
        self._arp_sample_counter: int           = 0
        self._arp_note_playing:   Optional[int] = None
        self._arp_gate_samples:   int           = int(60.0 / 120.0 * self.sample_rate * 0.5)
        self._arp_direction:      int           = 1   # +1 or -1 for up_down

        self.amp_level = 0.75
        self.amp_level_target = 0.75
        self.amp_level_current = 0.75
        self.amp_smoothing = 0.95
        self.master_gain_current = 1.0
        self.master_gain_target = 1.0
        self.master_volume = 1.0
        self.master_volume_target = 1.0
        self.amp_compensation = True

        # --- Smoothed filter / intensity parameters (target/current pattern) ---
        # DSP reads *_current; UI sets the raw attribute which routes to *_target via
        # the param_update handler. Matching the existing amp_level_target/current pattern.
        self.cutoff_current    = 2000.0   # tracks cutoff_target with 0.85 smoothing
        self.cutoff_target     = 2000.0
        self.cutoff_smoothing  = 0.85
        self.resonance_current   = 0.3
        self.resonance_target    = 0.3
        self.resonance_smoothing = 0.90
        self.intensity_current   = 0.8
        self.intensity_target    = 0.8
        self.intensity_smoothing = 0.90

        # Anti-click ramp after filter_mode switch (~10.7 ms at 48 kHz)
        self._filter_ramp_remaining = 0
        self._FILTER_RAMP_LEN       = 512

        # Output mute gate for randomize — fades out the mix before param changes
        # are applied (waveform/octave/envelope click suppression) then fades back in.
        # 384 samples ≈ 8ms at 48kHz: long enough to hide any waveform/frequency
        # discontinuity, short enough to be musically inaudible as a stutter.
        self._mute_ramp_remaining = 0   # samples of fade-out still pending
        self._mute_ramp_fadein    = 0   # samples of fade-in still pending
        self._MUTE_RAMP_LEN       = 384

        self.pitch_bend = 0.0
        self.pitch_bend_target = 0.0
        self.pitch_bend_smoothing = 0.85
        self.mod_wheel = 0.0

        self.voices: List[Voice] = [Voice(self.sample_rate, i) for i in range(self.num_voices)]
        self.held_notes: set = set()
        self.midi_event_queue = queue.Queue()

        if AUDIO_AVAILABLE and pyaudio is not None:
            try:
                self.audio = pyaudio.PyAudio()
                default_output = self.audio.get_default_output_device_info()
                self.stream = self.audio.open(
                    format=pyaudio.paInt16, channels=2, rate=self.sample_rate,
                    output=True, output_device_index=default_output['index'],
                    frames_per_buffer=self.buffer_size, stream_callback=self._audio_callback, start=False
                )
                self.stream.start_stream()
                self.running = True
                self._elevate_audio_priority()
            except Exception as e:
                print(f"Audio initialization failed: {e}")
                self.running = False

    def _elevate_audio_priority(self):
        """Raise process/thread scheduling priority so the PortAudio callback
        thread is not preempted by the Textual UI thread during widget rebuilds.

        Each OS has its own API — all three are handled:

        Windows  — SetPriorityClass(ABOVE_NORMAL_PRIORITY_CLASS) on the process.
                   No admin rights required.  ABOVE_NORMAL sits one step above
                   normal apps without needing the admin-gated REALTIME class.

        Linux    — Try SCHED_FIFO real-time scheduling for the current thread
                   via ctypes → pthread_setschedparam (requires CAP_SYS_NICE or
                   running as root). Falls back to os.nice(-10) if rt scheduling
                   is refused. Also sets PR_SET_TIMERSLACK to 100µs so the
                   kernel wakes this process more precisely on sleep expiry.

        macOS    — Try thread_policy_set(THREAD_TIME_CONSTRAINT_POLICY) via
                   ctypes → libSystem. This is the correct API for real-time
                   audio on Darwin; it is what Core Audio uses internally.
                   Falls back to os.nice(-10) if the Mach call fails.

        All failures are silent — the audio still works, it just has less
        OS-scheduling protection against UI-thread interference.
        """
        try:
            if sys.platform == "win32":
                # ----------------------------------------------------------------
                # Windows: elevate the whole process priority class.
                # ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
                # ----------------------------------------------------------------
                ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                ctypes.windll.kernel32.SetPriorityClass(handle, ABOVE_NORMAL_PRIORITY_CLASS)

            elif sys.platform == "linux":
                # ----------------------------------------------------------------
                # Linux: set SCHED_FIFO real-time scheduling on the current
                # thread.  pthread_setschedparam is the POSIX API for this.
                # SCHED_FIFO = 1, priority 10 (modest — well below max of 99
                # so the kernel watchdog can still preempt if needed).
                # ----------------------------------------------------------------
                SCHED_FIFO = 1
                RT_PRIORITY = 10
                try:
                    libpthread = ctypes.CDLL("libpthread.so.0", use_errno=True)
                    class SchedParam(ctypes.Structure):
                        _fields_ = [("sched_priority", ctypes.c_int)]
                    param = SchedParam(RT_PRIORITY)
                    # 0 = current thread
                    ret = libpthread.pthread_setschedparam(0, SCHED_FIFO, ctypes.byref(param))
                    if ret != 0:
                        raise OSError(ret, "pthread_setschedparam failed")
                except Exception:
                    # Fall back to process nice level — no CAP_SYS_NICE available
                    try:
                        os.nice(-10)
                    except Exception:
                        pass
                # PR_SET_TIMERSLACK = 29: sets timer slack to 100µs for this
                # process so clock_nanosleep wakes up tighter (default is 50µs
                # for the calling thread but 50ms for child threads on Linux).
                try:
                    PR_SET_TIMERSLACK = 29
                    libc = ctypes.CDLL("libc.so.6", use_errno=True)
                    libc.prctl(PR_SET_TIMERSLACK, ctypes.c_ulong(100000), 0, 0, 0)
                except Exception:
                    pass

            elif sys.platform == "darwin":
                # ----------------------------------------------------------------
                # macOS: use the Mach thread_policy_set with
                # THREAD_TIME_CONSTRAINT_POLICY — the same API Core Audio uses
                # for its own real-time threads.
                # Values below are conservative (5ms period, 2ms computation,
                # 3ms constraint) — safe for a 256-sample / 48kHz buffer which
                # has a ~5.3ms deadline.
                # ----------------------------------------------------------------
                THREAD_TIME_CONSTRAINT_POLICY = 2
                THREAD_TIME_CONSTRAINT_POLICY_COUNT = 4
                try:
                    libSystem = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)

                    class MachTimeConstraint(ctypes.Structure):
                        _fields_ = [
                            ("period",      ctypes.c_uint32),
                            ("computation", ctypes.c_uint32),
                            ("constraint",  ctypes.c_uint32),
                            ("preemptible", ctypes.c_int),
                        ]

                    # mach_timebase_info to convert ns → Mach absolute time units
                    class MachTimebaseInfo(ctypes.Structure):
                        _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]

                    tb = MachTimebaseInfo()
                    libSystem.mach_timebase_info(ctypes.byref(tb))
                    # Convert nanoseconds to Mach time units
                    def ns_to_mach(ns):
                        return int(ns * tb.denom / tb.numer)

                    policy = MachTimeConstraint(
                        period      = ns_to_mach(5_000_000),   # 5 ms period
                        computation = ns_to_mach(2_000_000),   # 2 ms compute budget
                        constraint  = ns_to_mach(3_000_000),   # 3 ms deadline
                        preemptible = 1,
                    )
                    thread_self = libSystem.mach_thread_self()
                    libSystem.thread_policy_set(
                        thread_self,
                        THREAD_TIME_CONSTRAINT_POLICY,
                        ctypes.byref(policy),
                        THREAD_TIME_CONSTRAINT_POLICY_COUNT,
                    )
                except Exception:
                    # Fall back to process nice level
                    try:
                        os.nice(-10)
                    except Exception:
                        pass

        except Exception:
            pass  # Non-fatal — never crash because of priority elevation failure

    # ── Arpeggiator helpers (audio-thread only) ──────────────────────

    def _arp_rebuild_sequence(self):
        """Rebuild the expanded note list from held notes and octave range.
        Sorted ascending, then octave-transposed copies are appended.
        Called whenever held notes or arp_range changes.
        """
        if not self._arp_held_notes:
            self._arp_sequence = []
            return
        base = sorted(set(self._arp_held_notes))
        seq  = []
        for shift in range(int(self.arp_range)):
            for note in base:
                t = note + shift * 12
                if t <= 127:
                    seq.append(t)
        self._arp_sequence = seq
        if seq:
            self._arp_index = self._arp_index % len(seq)

    def _arp_next_index(self) -> int:
        """Advance sequencer direction state and return the next note index."""
        n = len(self._arp_sequence)
        if n == 0:
            return 0
        if self.arp_mode == "up":
            idx = self._arp_index % n
            self._arp_index = (self._arp_index + 1) % n
        elif self.arp_mode == "down":
            idx = (n - 1 - self._arp_index % n)
            self._arp_index = (self._arp_index + 1) % n
        elif self.arp_mode == "up_down":
            idx = self._arp_index % n
            nxt = self._arp_index + self._arp_direction
            if nxt >= n:
                self._arp_direction = -1
                nxt = max(0, n - 2)
            elif nxt < 0:
                self._arp_direction = 1
                nxt = min(1, n - 1)
            self._arp_index = nxt
        else:  # "random"
            idx = _rnd.randrange(n)
            self._arp_index = idx
        return idx

    def _arp_recalc_timing(self):
        """Recompute step and gate sample counts from arp_bpm and arp_gate."""
        self._arp_step_samples = max(1, int(60.0 / max(1.0, self.arp_bpm) * self.sample_rate))
        self._arp_gate_samples = max(1, int(self._arp_step_samples * float(self.arp_gate)))

    def _midi_to_frequency(self, midi_note: int) -> float:
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

    def _update_voice_frequencies(self):
        if abs(self.pitch_bend - self.pitch_bend_target) > 0.0001:
            self.pitch_bend = self.pitch_bend * self.pitch_bend_smoothing + self.pitch_bend_target * (1.0 - self.pitch_bend_smoothing)
        else: self.pitch_bend = self.pitch_bend_target
        for v in self.voices:
            if v.base_frequency is not None and (v.note_active or v.is_releasing):
                v.frequency = v.base_frequency * (2.0 ** (self.pitch_bend / 12.0))

    def _generate_waveform(self, waveform: str, frequency: float, num_samples: int, start_phase: float) -> tuple[np.ndarray, float]:
        phase_inc = 2 * np.pi * frequency / self.sample_rate
        t = np.arange(num_samples)
        phases = start_phase + t * phase_inc
        t_norm = (phases / (2 * np.pi)) % 1.0
        if waveform == "pure_sine":
            samples = np.sin(phases)
        elif waveform == "sine":
            # Vintage-warm sine: fundamental + 1% 2nd harmonic for subtle colour.
            # Using sin(2*phase) instead of a sawtooth avoids the wrap discontinuity
            # that caused a periodic tick once per cycle at the phase-rollover point.
            samples = np.sin(phases) * 0.99 + np.sin(2.0 * phases) * 0.01
        elif waveform == "triangle":
            samples = 4.0 * np.abs(t_norm - 0.5) - 1.0
        elif waveform == "square":
            samples = np.where(np.sin(phases) >= 0, 1.0, -1.0)
        else:
            samples = 2.0 * t_norm - 1.0
        final_phase = (start_phase + num_samples * phase_inc) % (2 * np.pi)
        return samples.astype(np.float32), final_phase

    def _apply_envelope(self, voice: Voice, samples: np.ndarray, num_samples: int) -> np.ndarray:
        dt = 1.0 / self.sample_rate
        VEL_C, VEL_F = 1.3, 0.15
        v_scaled = VEL_F + (1.0 - VEL_F) * (voice.velocity ** VEL_C)
        v_int = self.intensity_current * v_scaled
        times = voice.envelope_time + np.arange(num_samples) * dt
        envelope = np.zeros(num_samples, dtype=np.float32)
        if voice.is_releasing:
            # rel_mod scales release time by note-off velocity (soft release -> longer tail).
            # time_const is the RC time constant of the exponential decay — the /4 divisor
            # that was here previously made releases sound 4x shorter than the UI indicated.
            rel_mod = 1.0 / (0.5 + voice.release_velocity)
            time_const = max(0.005, self.release * rel_mod)
            envelope = voice.release_start_level * np.exp(-times / time_const)
            ANTI_R = 0.002
            if times[0] < ANTI_R:
                mask = times < ANTI_R
                p = times[mask] / ANTI_R
                envelope[mask] = voice.release_start_level * (1.0 - p) + envelope[mask] * p
            voice.envelope_time = times[-1] + dt
            if envelope[-1] < 0.001 or times[-1] > self.release * 5: voice.reset()
        elif voice.note_active:
            atk_mask = times < self.attack
            if self.attack > 0: envelope[atk_mask] = (times[atk_mask] / self.attack) * v_int
            else: envelope[atk_mask] = v_int
            if voice.steal_start_level > 0.001:
                # 8ms linear crossfade from the stolen note's last level to the new
                # attack — long enough to be inaudible, short enough not to smear the
                # new note's transient.
                CROSS = 0.008
                if times[0] < CROSS:
                    mask = times < CROSS
                    p = times[mask] / CROSS          # linear 0->1 over 8ms
                    envelope[mask] = voice.steal_start_level * (1.0 - p) + envelope[mask] * p
                    if times[-1] >= CROSS: voice.steal_start_level = 0.0
            dec_end = self.attack + self.decay
            dec_mask = (times >= self.attack) & (times < dec_end)
            if self.decay > 0:
                p = (times[dec_mask] - self.attack) / self.decay
                envelope[dec_mask] = v_int * (1.0 - p * (1.0 - self.sustain))
            else: envelope[dec_mask] = v_int * self.sustain
            envelope[times >= dec_end] = v_int * self.sustain
            # ANTI_I: frequency-adaptive exponential fade-in applied to the onset window.
            # Duration matches onset_ms (set at trigger time to 1.5 × note period,
            # clamped [3ms, 30ms]) so the DC blocker's settling transient is suppressed
            # for the full duration it takes the blocker to reach steady-state at
            # very low frequencies (e.g. 27ms at 55 Hz vs the old fixed 5ms).
            # Applied AFTER the CROSS crossfade so stolen voices still start from
            # steal_start_level — ANTI_I only attenuates, never raises the envelope.
            ANTI_I = voice.onset_ms / 1000.0   # frequency-adaptive (3ms–30ms)
            if times[0] < ANTI_I:
                mask = times < ANTI_I
                envelope[mask] *= (1.0 - np.exp(-6.0 * (times[mask] / ANTI_I)))
            voice.envelope_time = times[-1] + dt
        voice.last_envelope_level = envelope[-1]
        return samples * envelope

    def _filter_process(self, samples: np.ndarray, cutoff: float, filter_type: str,
                        prev_state: float, res: float = 0.0,
                        prev_state_b: float = 0.0) -> tuple[np.ndarray, float, float]:
        """1-pole IIR filter with optional resonance cascade.

        Returns (filtered, state, state_b) where state_b is the second-pole
        state kept separately so both poles persist correctly across buffers.
        state_b is only meaningful when filter_type == 'lpf' and res > 0.1.
        """
        alpha = np.clip(2 * np.pi * cutoff / self.sample_rate, 0.0, 1.0)
        # res_fb: feedback coefficient. Capped at 0.95 to guarantee stability
        # across all cutoff frequencies including very high alpha values.
        res_fb = res * 0.95
        filtered = np.zeros_like(samples, dtype=np.float32)
        state = float(prev_state)
        for i in range(len(samples)):
            inp = samples[i] - res_fb * state
            state = alpha * inp + (1.0 - alpha) * state
            filtered[i] = state if filter_type == "lpf" else samples[i] - state

        # Second pole: runs on the output of the first pole using its OWN state
        # (prev_state_b), not state from pole 1.  This keeps the two integrators
        # independent so neither corrupts the other's memory across buffer boundaries.
        state_b = float(prev_state_b)
        if filter_type == "lpf" and res > 0.1:
            for i in range(len(filtered)):
                inp2 = filtered[i] - res_fb * 0.5 * state_b
                state_b = alpha * inp2 + (1.0 - alpha) * state_b
                filtered[i] = state_b

        return filtered, state, state_b

    def _filter_ladder_process(self, samples: np.ndarray, cutoff: float,
                               prev_states: list, res: float = 0.0) -> tuple:
        """4-pole Moog ladder filter — warm, strong resonance, self-oscillates near res=0.99.

        Uses one-sample-delayed feedback (inaudible at 48 kHz) so the per-sample
        computation is independent and the loop is simple to follow.
        Stilson-Smith k normalisation keeps stability across all cutoff frequencies.
        """
        sr = self.sample_rate
        fc = float(np.clip(cutoff, 20.0, sr * 0.45))
        alpha = float(np.clip(2.0 * np.pi * fc / sr, 0.0, 0.95))
        # k normalisation: resonance feedback scales down with alpha so the
        # filter remains unconditionally stable; k→1.0 approaches self-oscillation.
        k = float(np.clip(res * (1.0 / (1.0 + alpha)), 0.0, 0.99))

        N = len(samples)
        out = np.zeros(N, dtype=np.float32)
        s0, s1, s2, s3 = prev_states[0], prev_states[1], prev_states[2], prev_states[3]
        a1 = 1.0 - alpha

        for i in range(N):
            # Input saturated with global feedback from previous stage-4 output
            x0 = float(np.tanh(float(samples[i]) - 4.0 * k * s3))
            # Linear 4-pole cascade — input saturation alone gives adequate warmth
            s0 = a1 * s0 + alpha * x0
            s1 = a1 * s1 + alpha * s0
            s2 = a1 * s2 + alpha * s1
            s3 = a1 * s3 + alpha * s2
            out[i] = s3

        return out, [s0, s1, s2, s3]

    def _filter_svf_process(self, samples: np.ndarray, cutoff: float,
                            lp_state: float, bp_state: float,
                            res: float = 0.0) -> tuple:
        """Chamberlin State Variable Filter — 2-pole LP output.

        Uses the correct Chamberlin update order (lp updated from previous bp, not
        the newly-computed bp) which is unconditionally stable for f <= 2*sqrt(q/2).
        Cutoff is hard-limited to sr/6 (~8kHz at 48kHz) to stay in the stable region.
        q=2 (no resonance) → q→0 (near self-oscillation); clamped to prevent blow-up.
        """
        sr = self.sample_rate
        # Cap fc at sr/12 (~4kHz at 48kHz) to keep the f coefficient below ~0.5,
        # well within the Chamberlin SVF's unconditional stability region (f < sqrt(q)).
        # Higher cutoffs beyond this range are handled by the Ladder filter's character.
        fc = float(np.clip(cutoff, 20.0, sr / 12.0))
        f = float(np.clip(2.0 * np.sin(np.pi * fc / sr), 0.0, 0.5))
        q = float(np.clip(2.0 - 2.0 * res, 0.05, 2.0))

        N = len(samples)
        out = np.zeros(N, dtype=np.float32)
        lp = lp_state
        bp = bp_state

        for i in range(N):
            # Correct Chamberlin order: lp uses previous bp, bp uses current hp
            lp = lp + f * bp              # integrate bp → lp (previous bp)
            hp = float(samples[i]) - lp - q * bp
            bp = bp + f * hp              # integrate hp → bp
            # Hard-clamp states each sample to prevent runaway divergence
            if lp > 4.0:  lp = 4.0
            elif lp < -4.0: lp = -4.0
            if bp > 4.0:  bp = 4.0
            elif bp < -4.0: bp = -4.0
            out[i] = lp

        return out, lp, bp

    def _apply_filter(self, voice: Voice, samples: np.ndarray, rank: int = 1, cutoff_mod: float = 1.0) -> np.ndarray:
        f_base = voice.base_frequency or 440.0
        track_mult = 1.0 + 0.5 * (f_base / 440.0 - 1.0)
        vel_mult = 0.7 + (voice.velocity * 0.6)
        # Use smoothed cutoff_current to avoid step-discontinuity clicks on cutoff changes
        fl_lpf = float(np.clip(self.cutoff_current * cutoff_mod * track_mult * vel_mult, 20.0, 20000.0))
        fl_hpf = float(np.clip(self.hpf_cutoff * track_mult * vel_mult, 20.0, fl_lpf / 2.0))

        # alpha_norm: shared per-frame coefficient used for gain normalisation below.
        # Both filter methods compute the same alpha internally; computing it here
        # once keeps the normalisation consistent across modes.
        alpha_norm = float(np.clip(2.0 * np.pi * fl_lpf / self.sample_rate, 0.0001, 0.95))

        # HPF: legacy 1-pole IIR (unchanged)
        hpf_s = voice.filter_state_hpf1 if rank == 1 else voice.filter_state_hpf2
        samples, hpf_s, _ = self._filter_process(samples, fl_hpf, "hpf", hpf_s, 0.0)
        if rank == 1: voice.filter_state_hpf1 = hpf_s
        else:         voice.filter_state_hpf2 = hpf_s

        # Gain normalisation: both modes use the same 1/alpha formula so they stay
        # volume-matched to each other and to the old 1-pole reference behaviour.
        # Ceiling of 8.0 prevents float32 overflow at very low cutoff and limits
        # extreme boost; floor of 1.0 means the filter never reduces gain below
        # the un-compensated level (a fully-open filter should not lose loudness).
        filter_comp = float(np.clip(1.0 / alpha_norm, 1.0, 8.0))

        # LPF: dispatch on filter_mode, using smoothed resonance_current
        if self.filter_mode == "svf":
            lp_s = voice.filter_state_svf1_lp if rank == 1 else voice.filter_state_svf2_lp
            bp_s = voice.filter_state_svf1_bp if rank == 1 else voice.filter_state_svf2_bp
            filtered, lp_s, bp_s = self._filter_svf_process(
                samples, fl_lpf, lp_s, bp_s, self.resonance_current)
            if rank == 1: voice.filter_state_svf1_lp, voice.filter_state_svf1_bp = lp_s, bp_s
            else:         voice.filter_state_svf2_lp, voice.filter_state_svf2_bp = lp_s, bp_s
        else:  # "ladder" (default)
            ladder_s = voice.filter_state_ladder1 if rank == 1 else voice.filter_state_ladder2
            filtered, ladder_s = self._filter_ladder_process(
                samples, fl_lpf, ladder_s, self.resonance_current)
            if rank == 1: voice.filter_state_ladder1 = ladder_s
            else:         voice.filter_state_ladder2 = ladder_s

        return filtered * filter_comp

    def _apply_dc_blocker(self, voice: Voice, samples: np.ndarray) -> np.ndarray:
        """First-order HPF DC blocker with frequency-adaptive pole.

        Standard coeff=0.999 places the pole at 2.4 Hz — fine for mid/high notes
        but produces an 87.5° phase shift at 55 Hz (octave=-2 sine), causing the
        blocker to differentiate the onset waveform into a visible/audible thump.

        Adaptive strategy: above 100 Hz use the standard 0.9990 (aggressive DC
        removal, negligible phase error at the fundamental).  Below 100 Hz linearly
        interpolate toward 0.9997 (pole ≈ 0.7 Hz, phase shift at 55 Hz ≈ 83°),
        giving the blocker a softer high-pass response that distorts the onset
        shape less — the onset ramp (Fix I) hides the remaining transient.

        Coefficient table:
          f0 ≥ 100 Hz : 0.9990  (pole 2.4 Hz, phase at f0 < 5°  for most notes)
          f0 = 75 Hz  : 0.9993  (pole 1.7 Hz)
          f0 = 50 Hz  : 0.9997  (pole 0.7 Hz)
          f0 < 50 Hz  : 0.9997  (clamped — already very low pole)
        """
        f0 = voice.frequency or 440.0
        if f0 >= 100.0:
            coeff = 0.9990
        elif f0 >= 50.0:
            # Linear interpolation: t=0 at 50 Hz → coeff=0.9997; t=1 at 100 Hz → coeff=0.9990
            t = (f0 - 50.0) / 50.0
            coeff = 0.9997 - t * 0.0007
        else:
            coeff = 0.9997

        xp, yp = voice.dc_blocker_x, voice.dc_blocker_y
        filtered = np.zeros_like(samples)
        for i in range(len(samples)):
            filtered[i] = samples[i] - xp + coeff * yp
            xp, yp = samples[i], filtered[i]
        voice.dc_blocker_x, voice.dc_blocker_y = xp, yp
        return filtered

    def _sanitize_signal(self, samples: np.ndarray) -> np.ndarray:
        """Replace NaN/Inf with zeros and hard-clip to ±2.0.

        Guards against NaN propagation from gain compensation at extreme alpha values.
        Called at the filter output stage — the only pipeline point where gain
        multiplication could theoretically produce Inf despite the formula clamping.
        ±2.0 ceiling is above tanh's linear region (tanh(2)≈0.964) so normal peaks
        are unaffected; only pathological values are clipped.
        """
        samples = np.where(np.isfinite(samples), samples, 0.0)
        return np.clip(samples, -2.0, 2.0)

    def _process_midi_events(self):
        """Drain the event queue at the start of each audio callback.

        Event types and their per-buffer limits:
        - 'param_update'  : ALL drained immediately — parameters must apply
                            in the next buffer without delay, and they carry no
                            click risk because they go through smoothing ramps.
        - 'all_notes_off' : ALL drained immediately — silence must be instant.
        - 'note_on' / 'note_off' : capped at 3 per buffer to spread rapid
                            polyphony changes across consecutive buffers, giving
                            the master_gain ramp time to track the voice count
                            gradually and avoid step-discontinuity clicks.
        """
        note_events_processed = 0
        # First pass: drain ALL non-note events (params, control) with no cap.
        # These are applied on the audio thread so there is no race with the
        # DSP code that follows in the same callback invocation.
        pending_notes = []
        while True:
            try:
                e = self.midi_event_queue.get_nowait()
            except Exception:
                break
            if e['type'] == 'param_update':
                # Apply parameter writes on the audio thread — eliminates the
                # UI-thread vs audio-thread race on all 25+ shared attributes.
                for k, v in e['params'].items():
                    if hasattr(self, k):
                        if k == 'amp_level':       self.amp_level_target     = v
                        elif k == 'master_volume': self.master_volume_target  = v
                        elif k == 'cutoff':        self.cutoff_target         = v
                        elif k == 'resonance':     self.resonance_target      = v
                        elif k == 'intensity':     self.intensity_target      = v
                        else:
                            setattr(self, k, v)
                            # On filter mode change, zero all per-voice LPF states to
                            # prevent stale state from the previous filter bleeding through,
                            # and arm the fade-in ramp to suppress the state-zeroing transient.
                            if k == 'filter_mode':
                                for voice in self.voices:
                                    voice.filter_state_ladder1 = [0.0, 0.0, 0.0, 0.0]
                                    voice.filter_state_ladder2 = [0.0, 0.0, 0.0, 0.0]
                                    voice.filter_state_svf1_lp = voice.filter_state_svf1_bp = 0.0
                                    voice.filter_state_svf2_lp = voice.filter_state_svf2_bp = 0.0
                                    voice.filter_state_lpf1    = voice.filter_state_lpf1b   = 0.0
                                    voice.filter_state_lpf2    = voice.filter_state_lpf2b   = 0.0
                                self._filter_ramp_remaining = self._FILTER_RAMP_LEN
                            elif k == 'delay_time':
                                # Recalculate integer sample count when delay time changes.
                                self.delay_time    = float(v)
                                self._delay_samples = max(1, min(
                                    int(v * self.sample_rate),
                                    len(self._delay_buf_l) - 1))
                            elif k == 'arp_bpm':
                                self.arp_bpm = float(v); self._arp_recalc_timing()
                            elif k == 'arp_gate':
                                self.arp_gate = float(v); self._arp_recalc_timing()
                            elif k == 'arp_range':
                                self.arp_range = int(v); self._arp_rebuild_sequence()
                            elif k == 'arp_enabled':
                                self.arp_enabled = bool(v)
                                if not self.arp_enabled:
                                    if self._arp_note_playing is not None:
                                        self._release_note(self._arp_note_playing)
                                        self._arp_note_playing = None
                                self._arp_sample_counter = 0
                            elif k == 'arp_mode':
                                self.arp_mode = v
                                self._arp_index = 0; self._arp_direction = 1
            elif e['type'] == 'all_notes_off':
                # Reset voices on the audio thread — safe between DSP buffers.
                for v in self.voices:
                    v.reset()
                # Also clear arpeggiator state.
                self._arp_held_notes.clear(); self._arp_sequence.clear()
                self._arp_note_playing = None; self._arp_sample_counter = 0
            elif e['type'] == 'mute_gate':
                # Arm a short output fade-out so that instantly-applied params
                # (waveform, octave, envelope) from action_randomize don't click.
                # The fade-in is automatically queued when the fade-out completes
                # (see _audio_callback).  Re-arming while already fading re-starts
                # from the current ramp position so rapid randomize presses stay clean.
                self._mute_ramp_remaining = self._MUTE_RAMP_LEN
                self._mute_ramp_fadein    = 0
            else:
                # note_on / note_off — collect and process below with the cap.
                pending_notes.append(e)

        # Second pass: process note events with the 3-per-buffer cap.
        # When arp is enabled, note_on/note_off update the held-note list and
        # rebuild the arp sequence rather than triggering voices directly.
        for e in pending_notes:
            if note_events_processed >= 3:
                # Re-enqueue remaining note events for the next buffer.
                self.midi_event_queue.put(e)
            else:
                if e['type'] == 'note_on':
                    if self.arp_enabled:
                        n = e['note']
                        if n not in self._arp_held_notes:
                            self._arp_held_notes.append(n)
                        self._arp_rebuild_sequence()
                        self.held_notes.add(n)
                    else:
                        self._trigger_note(e['note'], e['velocity'])
                    note_events_processed += 1
                elif e['type'] == 'note_off':
                    n = e['note']
                    if self.arp_enabled:
                        if n in self._arp_held_notes:
                            self._arp_held_notes.remove(n)
                        self._arp_rebuild_sequence()
                        # If all keys released, stop the current arp note
                        if not self._arp_held_notes and self._arp_note_playing is not None:
                            self._release_note(self._arp_note_playing)
                            self._arp_note_playing = None
                        self.held_notes.discard(n)
                    else:
                        self._release_note(e['note'], e.get('velocity', 0.5))
                    note_events_processed += 1

    def _trigger_note(self, note: int, vel: float):
        freq = self._midi_to_frequency(note)
        # Frequency-adaptive onset window: scale with the note period so the DC
        # blocker's startup transient is hidden under the onset ramp even for very
        # low notes.  Formula: 1.5 × period_ms, clamped [3ms, 30ms].
        # Examples: 440 Hz → 3ms (unchanged); 110 Hz → 13.5ms; 55 Hz → 27ms.
        period_ms = (1000.0 / freq) if freq > 0 else 3.0
        onset_ms_for_note = max(3.0, min(30.0, period_ms * 1.5))
        for v in self.voices:
            if v.midi_note == note and v.note_active:
                v.trigger(note, freq, vel)
                v.onset_ms = onset_ms_for_note
                return
        for v in self.voices:
            if v.is_available():
                v.trigger(note, freq, vel)
                v.onset_ms = onset_ms_for_note
                return
        best_v, best_p, best_s = None, -1, -1.0
        for v in self.voices:
            p = 2 if (v.is_releasing and v.midi_note not in self.held_notes) else (1 if v.is_releasing else 0)
            s = v.envelope_time if v.is_releasing else v.age
            if p > best_p or (p == best_p and s > best_s): best_p, best_s, best_v = p, s, v
        if best_v:
            # Zero the filter and DC blocker states before triggering so the new
            # note's frequency doesn't collide with stale filter memory from the
            # stolen note. The CROSS envelope crossfade in _apply_envelope handles
            # amplitude continuity, while this prevents a frequency-domain glitch
            # in the first few filter output samples.
            best_v.filter_state_lpf1 = best_v.filter_state_hpf1 = 0.0
            best_v.filter_state_lpf2 = best_v.filter_state_hpf2 = 0.0
            best_v.filter_state_lpf1b = best_v.filter_state_lpf2b = 0.0
            best_v.dc_blocker_x = best_v.dc_blocker_y = 0.0
            best_v.trigger(note, freq, vel)
            best_v.onset_ms = onset_ms_for_note

    def _release_note(self, note: int, velocity: float = 0.5):
        for v in self.voices:
            if v.midi_note == note and v.note_active: v.release(self.attack, self.decay, self.sustain, self.intensity, velocity)

    def _audio_callback(self, in_data, frame_count, time_info, status):
        try:
            self._process_midi_events()
            self._update_voice_frequencies()
            if abs(self.amp_level_current - self.amp_level_target) > 0.0001:
                self.amp_level_current = self.amp_level_current * self.amp_smoothing + self.amp_level_target * (1.0 - self.amp_smoothing)
            else: self.amp_level_current = self.amp_level_target
            if abs(self.master_volume - self.master_volume_target) > 0.001:
                self.master_volume = self.master_volume * 0.9 + self.master_volume_target * 0.1
            else: self.master_volume = self.master_volume_target

            # --- Per-buffer parameter smoothing: cutoff, resonance, intensity ---
            # Eliminates clicks from hard parameter step-changes mid-playback.
            if abs(self.cutoff_current - self.cutoff_target) > 0.5:
                self.cutoff_current = (self.cutoff_current * self.cutoff_smoothing
                                       + self.cutoff_target * (1.0 - self.cutoff_smoothing))
            else:
                self.cutoff_current = self.cutoff_target
            if abs(self.resonance_current - self.resonance_target) > 0.001:
                self.resonance_current = (self.resonance_current * self.resonance_smoothing
                                          + self.resonance_target * (1.0 - self.resonance_smoothing))
            else:
                self.resonance_current = self.resonance_target
            if abs(self.intensity_current - self.intensity_target) > 0.001:
                self.intensity_current = (self.intensity_current * self.intensity_smoothing
                                          + self.intensity_target * (1.0 - self.intensity_smoothing))
            else:
                self.intensity_current = self.intensity_target

            # ── LFO (shape-aware, single depth + target routing) ────────────
            lfo_phase_prev = self.lfo_phase
            lfo_phase_inc  = 2.0 * np.pi * self.lfo_freq * frame_count / self.sample_rate
            self.lfo_phase = (self.lfo_phase + lfo_phase_inc) % (2.0 * np.pi)
            if self.lfo_shape == "triangle":
                t_norm = lfo_phase_prev / (2.0 * np.pi)
                lfo_val = float(4.0 * abs(t_norm - 0.5) - 1.0)
            elif self.lfo_shape == "square":
                lfo_val = 1.0 if lfo_phase_prev < np.pi else -1.0
            elif self.lfo_shape == "sample_hold":
                # Phase wrap signals a new S&H period — sample a new random value.
                # Safe check: if prev > current the modulo wrapped (lfo_freq is
                # capped well below a full cycle per buffer so double-wrap can't happen).
                if lfo_phase_prev > self.lfo_phase:
                    self._lfo_sh_value = _rnd.uniform(-1.0, 1.0)
                lfo_val = self._lfo_sh_value
            else:  # "sine" (default)
                lfo_val = float(np.sin(lfo_phase_prev))
            # Route lfo_depth to the correct destination(s); legacy per-dest mods
            # (lfo_vco_mod / lfo_vcf_mod / lfo_vca_mod) are retained for backward
            # compat with old presets — new UI only writes lfo_depth + lfo_target.
            d = float(self.lfo_depth)
            if self.lfo_target == "vco":
                vco_mod, vcf_mod, vca_mod = d, 0.0, 0.0
            elif self.lfo_target == "vcf":
                vco_mod, vcf_mod, vca_mod = 0.0, d, 0.0
            elif self.lfo_target == "vca":
                vco_mod, vcf_mod, vca_mod = 0.0, 0.0, d
            else:  # "all"
                vco_mod = vcf_mod = vca_mod = d
            # Also blend in any legacy per-dest mods from old presets/API callers
            vco_lfo = 1.0 + lfo_val * (vco_mod + self.lfo_vco_mod) * 0.05
            vcf_lfo = 1.0 + lfo_val * (vcf_mod + self.lfo_vcf_mod) * 0.5
            vca_lfo = 1.0 + lfo_val * (vca_mod + self.lfo_vca_mod) * 0.3

            mixed_l = np.zeros(frame_count, dtype=np.float32)
            mixed_r = np.zeros(frame_count, dtype=np.float32)

            # ── Arpeggiator clock (audio-thread driven, sample-accurate) ────
            # The counter advances by frame_count each buffer; when it reaches
            # a step boundary we trigger the next note in the sequence and
            # release the previous one at the gate boundary.  The remainder is
            # carried over so the beat grid drifts by at most 1 sample over
            # any number of steps (no cumulative phase error from integer
            # rounding).
            if self.arp_enabled and self._arp_sequence:
                self._arp_sample_counter += frame_count
                # Gate-off: release the playing note once the gate window expires
                if (self._arp_note_playing is not None
                        and self._arp_sample_counter > self._arp_gate_samples):
                    self._release_note(self._arp_note_playing)
                    self._arp_note_playing = None
                # Step: fire the next note when a full step has elapsed
                if self._arp_sample_counter >= self._arp_step_samples:
                    # Carry the remainder so timing stays phase-accurate
                    self._arp_sample_counter -= self._arp_step_samples
                    idx  = self._arp_next_index()
                    note = self._arp_sequence[idx]
                    self._trigger_note(note, 1.0)
                    self._arp_note_playing = note

            # Pre-count active voices BEFORE mixing so master_gain_target is
            # updated from the correct count and gain_ramp covers the full
            # transition in this buffer rather than lagging one buffer behind.
            active_count = sum(1 for v in self.voices if v.note_active or v.is_releasing)

            # Compute gain target from the pre-counted voice count and update
            # the smoothed current value BEFORE capturing gain_prev so the ramp
            # goes from last buffer's end to this buffer's correct target.
            if active_count == 0:
                # Decay master_gain smoothly back toward 1.0 rather than snapping
                # it instantly. This prevents a gain step-jump on the next note_on
                # that arrives after a short silence (previously gain was hard-reset
                # to 1.0, so the first buffer of the new note always started too loud).
                self.master_gain_target = 1.0
                self.master_gain_current = self.master_gain_current * 0.90 + 1.0 * 0.10
                return (np.zeros(frame_count * 2, dtype=np.int16).tobytes(), pyaudio.paContinue)

            self.master_gain_target = 1.0 / np.sqrt(active_count) if active_count > 1 else 1.0
            # Snapshot gain AFTER the target is known but BEFORE smoothing,
            # so gain_ramp interpolates from the previous buffer's settled value
            # to the new smoothed value — a true per-sample continuous transition.
            gain_prev = self.master_gain_current
            # Faster coefficient (0.80) so the gain tracks voice-count changes
            # within ~2 buffers (~10ms) rather than drifting for 50ms+.
            self.master_gain_current = self.master_gain_current * 0.80 + self.master_gain_target * 0.20
            # Per-sample gain ramp: eliminates the buffer-boundary step discontinuity
            # that caused clicks when active_count changed between buffers.
            gain_ramp = np.linspace(gain_prev, self.master_gain_current, frame_count, dtype=np.float32)

            for v in self.voices:
                if v.note_active or v.is_releasing:
                    p1_s, p2_s = v.phase, v.phase2
                    f1 = v.frequency * vco_lfo if v.frequency else 440.0
                    if self.octave_enabled and self.octave != 0: f1 *= (2.0 ** self.octave)
                    s1, v.phase = self._generate_waveform(self.waveform, f1, frame_count, p1_s)
                    s1 = self._sanitize_signal(self._apply_filter(v, s1, rank=1, cutoff_mod=vcf_lfo))
                    if self.rank2_enabled:
                        f2 = f1 * (2.0 ** (self.rank2_detune / 1200.0))
                        s2, v.phase2 = self._generate_waveform(self.rank2_waveform, f2, frame_count, p2_s)
                        s2 = self._sanitize_signal(self._apply_filter(v, s2, rank=2, cutoff_mod=vcf_lfo))
                        v_samples = s1 * (1.0 - self.rank2_mix) + s2 * self.rank2_mix
                    else:
                        v_samples = s1
                    if self.sine_mix > 0:
                        # Use and advance the voice's dedicated sine_phase accumulator
                        # so the sub-oscillator is phase-continuous across buffer boundaries.
                        ss, v.sine_phase = self._generate_waveform("pure_sine", f1, frame_count, v.sine_phase)
                        v_samples += ss * self.sine_mix
                    v_samples = self._apply_envelope(v, v_samples, frame_count) * vca_lfo
                    # Per-voice onset ramp: a frequency-adaptive linear fade-in applied
                    # to the post-envelope signal before the DC blocker.  The DC blocker
                    # resets to zero on every new trigger; if the signal is non-zero at
                    # sample 0 the blocker differentiates a large first step into a
                    # high-frequency click. Fading in over ONSET_RAMP samples ensures
                    # the blocker starts from near-zero signal regardless of oscillator
                    # phase or attack setting.
                    #
                    # Duration = v.onset_ms (set at trigger time to max(3ms, min(30ms,
                    # 1.5 × period_ms))).  At 440 Hz this is 3ms (~144 smp, unchanged).
                    # At 55 Hz this is 27ms (~1296 smp), covering the DC blocker's full
                    # settling time at that frequency.
                    ONSET_RAMP = int(self.sample_rate * v.onset_ms / 1000.0)
                    if v.onset_samples < ONSET_RAMP:
                        n = min(frame_count, ONSET_RAMP - v.onset_samples)
                        ramp = np.ones(frame_count, dtype=np.float32)
                        ramp[:n] = np.linspace(
                            v.onset_samples / ONSET_RAMP,
                            min((v.onset_samples + n) / ONSET_RAMP, 1.0),
                            n, dtype=np.float32
                        )
                        v_samples = v_samples * ramp
                        v.onset_samples += frame_count
                    v_samples = self._apply_dc_blocker(v, v_samples)
                    ang = v.pan * np.pi / 2
                    mixed_l += v_samples * np.cos(ang)
                    mixed_r += v_samples * np.sin(ang)
            # ── BBD-style Chorus (bypass when chorus_mix == 0) ───────────────
            # All taps read from the same shared ring buffer. Four LFO phases
            # spaced 90° apart (set at init) advance every sample by
            # 2π * chorus_rate / sample_rate so the modulation is continuous
            # across buffer boundaries. Base delay 0.5ms + depth-modulated swing
            # up to ±25ms. wet/dry mix controls the blend.
            if self.chorus_mix > 0.0:
                n_voices  = int(np.clip(self.chorus_voices, 1, 4))
                buf_len   = len(self._chorus_buf_l)
                max_dly_s = self.sample_rate * 0.025   # 25 ms in samples
                base_dly  = max(1, int(self.sample_rate * 0.0005))   # 0.5 ms base
                phase_inc = 2.0 * np.pi * self.chorus_rate / self.sample_rate
                cho_l = np.zeros(frame_count, dtype=np.float32)
                cho_r = np.zeros(frame_count, dtype=np.float32)
                for i in range(frame_count):
                    wp = self._chorus_write % buf_len
                    self._chorus_buf_l[wp] = mixed_l[i]
                    self._chorus_buf_r[wp] = mixed_r[i]
                    wet_l = wet_r = 0.0
                    for vi in range(n_voices):
                        self._chorus_phases[vi] = (self._chorus_phases[vi] + phase_inc) % (2.0 * np.pi)
                        mod_smp = int(np.sin(self._chorus_phases[vi]) * self.chorus_depth * max_dly_s)
                        rp = (wp - max(1, base_dly + mod_smp)) % buf_len
                        wet_l += self._chorus_buf_l[rp]
                        wet_r += self._chorus_buf_r[rp]
                    self._chorus_write = (wp + 1) % buf_len
                    scale = 1.0 / n_voices
                    mx    = float(self.chorus_mix)
                    cho_l[i] = mixed_l[i] * (1.0 - mx) + wet_l * scale * mx
                    cho_r[i] = mixed_r[i] * (1.0 - mx) + wet_r * scale * mx
                mixed_l = cho_l
                mixed_r = cho_r

            # ── FX Delay (stereo; bypass when delay_mix == 0) ─────────────────
            # Per-sample feedback loop writes input + feedback into the ring
            # buffer and reads back the delayed copy ds samples ago. Feedback
            # coefficient controls echo density; mix blends wet on top of dry.
            if self.delay_mix > 0.0:
                buf_len = len(self._delay_buf_l)
                dm  = float(self.delay_mix)
                fb  = float(self.delay_feedback)
                ds  = int(self._delay_samples)
                for i in range(frame_count):
                    wp  = self._delay_write % buf_len
                    rp  = (wp - ds) % buf_len
                    wet_l = self._delay_buf_l[rp]
                    wet_r = self._delay_buf_r[rp]
                    self._delay_buf_l[wp] = mixed_l[i] + fb * wet_l
                    self._delay_buf_r[wp] = mixed_r[i] + fb * wet_r
                    mixed_l[i] = mixed_l[i] * (1.0 - dm) + wet_l * dm
                    mixed_r[i] = mixed_r[i] * (1.0 - dm) + wet_r * dm
                    self._delay_write = (wp + 1) % buf_len

            # comp normalises waveform RMS to roughly the same perceived loudness.
            # Kept intentionally modest (≤1.0 for sine) so that at default amp_level
            # (0.75) and sustain (0.7) the pre-tanh drive stays below ~0.5 — well
            # inside tanh's linear region.  This prevents the attack transient from
            # saturating harder than the sustain, which was causing the visible
            # peak-then-sag shape in recorded waveforms.

            # --- Filter mode switch anti-click: fade in the mix over ~10.7 ms ---
            # Applied before tanh so the linear ramp is not distorted by high drive.
            if self._filter_ramp_remaining > 0:
                ramp_start = 1.0 - (self._filter_ramp_remaining / self._FILTER_RAMP_LEN)
                ramp_end   = 1.0 - max(0, self._filter_ramp_remaining - frame_count) / self._FILTER_RAMP_LEN
                ramp = np.linspace(ramp_start, ramp_end, frame_count, dtype=np.float32)
                mixed_l *= ramp
                mixed_r *= ramp
                self._filter_ramp_remaining = max(0, self._filter_ramp_remaining - frame_count)

            # --- Randomize mute gate: ~8ms fade-out then ~8ms fade-in (~384 smp each) ---
            # The mute_gate event arms _mute_ramp_remaining.  While it counts down the
            # mix fades to silence.  At zero it arms _mute_ramp_fadein so the next
            # buffer(s) fade back in — by then the new params are already active.
            # Both the mute_gate event and the param_update events are drained in the
            # same _process_midi_events() call, so the newly randomized waveform/octave
            # are already set before the fade-in plays — no click is audible.
            if self._mute_ramp_remaining > 0:
                ramp_start = self._mute_ramp_remaining / self._MUTE_RAMP_LEN
                ramp_end   = max(0, self._mute_ramp_remaining - frame_count) / self._MUTE_RAMP_LEN
                ramp = np.linspace(ramp_start, ramp_end, frame_count, dtype=np.float32)
                mixed_l *= ramp
                mixed_r *= ramp
                self._mute_ramp_remaining = max(0, self._mute_ramp_remaining - frame_count)
                if self._mute_ramp_remaining == 0:
                    self._mute_ramp_fadein = self._MUTE_RAMP_LEN  # arm fade-in

            if self._mute_ramp_fadein > 0:
                ramp_start = 1.0 - (self._mute_ramp_fadein / self._MUTE_RAMP_LEN)
                ramp_end   = 1.0 - max(0, self._mute_ramp_fadein - frame_count) / self._MUTE_RAMP_LEN
                ramp = np.linspace(ramp_start, ramp_end, frame_count, dtype=np.float32)
                mixed_l *= ramp
                mixed_r *= ramp
                self._mute_ramp_fadein = max(0, self._mute_ramp_fadein - frame_count)

            comp = 0.9 if self.waveform in ["sine", "pure_sine"] else (0.6 if self.waveform == "square" else 1.1)
            # drive controls soft-clip saturation character — amp_level only.
            # master_volume is applied AFTER tanh as a clean linear gain so both
            # controls have full, independent audible range without cancelling each other.
            drive = self.amp_level_current * comp
            mixed_l = np.tanh(mixed_l * drive * gain_ramp) * self.master_volume
            mixed_r = np.tanh(mixed_r * drive * gain_ramp) * self.master_volume
            out = np.empty(frame_count * 2, dtype=np.int16)
            out[0::2] = np.clip(mixed_l * 32767, -32767, 32767)
            out[1::2] = np.clip(mixed_r * 32767, -32767, 32767)
            return (out.tobytes(), pyaudio.paContinue)
        except Exception as e:
            return (np.zeros(frame_count * 2, dtype=np.int16).tobytes(), pyaudio.paContinue)

    def note_on(self, note: int, velocity: int = 127):
        self.held_notes.add(note)
        self.midi_event_queue.put({'type': 'note_on', 'note': note, 'velocity': velocity / 127.0})

    def note_off(self, note: int, velocity: int = 0):
        self.held_notes.discard(note)
        self.midi_event_queue.put({'type': 'note_off', 'note': note, 'velocity': velocity / 127.0})

    def all_notes_off(self):
        """Silence all voices. Called from the UI thread (mode switch, panic).

        Routes the reset through the event queue so it executes on the audio
        thread at the start of the next buffer — never mid-callback, which
        previously caused torn voice state and crackles during mode switches.
        """
        self.held_notes.clear()
        self.midi_event_queue.put({'type': 'all_notes_off'})

    def pitch_bend_change(self, value: int): self.pitch_bend_target = ((value - 8192) / 8192.0) * 2.0

    def modulation_change(self, value: int): self.mod_wheel = value / 127.0

    def update_parameters(self, **kwargs):
        """Update synth parameters from the UI thread.

        All writes are enqueued and applied on the audio thread at the start
        of the next buffer via _process_midi_events(). This eliminates the
        25+ shared-attribute race conditions between the Textual UI event loop
        and the PyAudio callback thread that caused clicks when knobs were
        moved while notes were playing.
        """
        self.midi_event_queue.put({'type': 'param_update', 'params': kwargs})

    def close(self):
        self.running = False
        if self.stream: self.stream.stop_stream(); self.stream.close()
        if self.audio: self.audio.terminate()

    def is_available(self) -> bool: return AUDIO_AVAILABLE and self.running

    def warm_up(self):
        if self.is_available(): self.note_on(0, 1); self.note_off(0)
