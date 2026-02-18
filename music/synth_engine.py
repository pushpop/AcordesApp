"""Synthesizer engine for generating audio waveforms."""
import os
import sys
import ctypes
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

        # RESET filter/DC memory if starting from silence OR if this is a voice steal
        # (same voice being retaken by a different note). Preserving stale filter/DC
        # state from the stolen note would cause a DC sag at the start of the new note.
        if True:  # always reset — free-running phase is preserved, states are not
            self.filter_state_lpf1 = self.filter_state_hpf1 = 0.0
            self.filter_state_lpf2 = self.filter_state_hpf2 = 0.0
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

        self.lfo_freq = 1.0
        self.lfo_vco_mod = 0.0
        self.lfo_vcf_mod = 0.0
        self.lfo_vca_mod = 0.0
        self.lfo_phase = 0.0

        self.amp_level = 0.75
        self.amp_level_target = 0.75
        self.amp_level_current = 0.75
        self.amp_smoothing = 0.95
        self.master_gain_current = 1.0
        self.master_gain_target = 1.0
        self.master_volume = 1.0
        self.master_volume_target = 1.0
        self.amp_compensation = True

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
        v_int = self.intensity * v_scaled
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
            # ANTI_I: 5ms exponential fade-in applied to the entire onset window.
            # Runs unconditionally (not gated on times[0] < ANTI_I) so it covers
            # cases where the first buffer is larger than ANTI_I. Applied AFTER
            # the CROSS crossfade so stolen voices still start from steal_start_level
            # rather than from zero — the two mechanisms compose correctly because
            # ANTI_I only attenuates, it never raises the envelope above its current value.
            ANTI_I = 0.005   # 5ms — covers the DC blocker's settling window
            if times[0] < ANTI_I:
                mask = times < ANTI_I
                envelope[mask] *= (1.0 - np.exp(-6.0 * (times[mask] / ANTI_I)))
            voice.envelope_time = times[-1] + dt
        voice.last_envelope_level = envelope[-1]
        return samples * envelope

    def _filter_process(self, samples: np.ndarray, cutoff: float, filter_type: str, prev_state: float, res: float = 0.0) -> tuple[np.ndarray, float]:
        # Standard 1-pole IIR: alpha is the feed-forward gain, (1-alpha) is the feedback pole.
        # Resonance is applied as negative feedback from the output subtracted from the input
        # BEFORE the integrator — this is the correct topology for a resonant 1-pole LPF.
        alpha = np.clip(2 * np.pi * cutoff / self.sample_rate, 0.0, 1.0)
        res_fb = res * 0.9  # keep well below 1.0 to stay stable
        filtered = np.zeros_like(samples, dtype=np.float32)
        state = float(prev_state)
        for i in range(len(samples)):
            inp = samples[i] - res_fb * state   # resonance feedback subtracted from input
            state = alpha * inp + (1.0 - alpha) * state
            filtered[i] = state if filter_type == "lpf" else samples[i] - state
        return filtered, state

    def _apply_filter(self, voice: Voice, samples: np.ndarray, rank: int = 1, cutoff_mod: float = 1.0) -> np.ndarray:
        lpf_s = voice.filter_state_lpf1 if rank == 1 else voice.filter_state_lpf2
        hpf_s = voice.filter_state_hpf1 if rank == 1 else voice.filter_state_hpf2
        # Use base_frequency (pre-octave) for keyboard tracking so the octave shift
        # applied in the audio callback is not counted a second time here.
        f_base = voice.base_frequency or 440.0
        track_mult = 1.0 + 0.5 * (f_base / 440.0 - 1.0)
        vel_mult = 0.7 + (voice.velocity * 0.6)
        fl_lpf = np.clip(self.cutoff * cutoff_mod * track_mult * vel_mult, 20.0, 20000.0)
        # Guard: HPF must always sit at least one octave below the LPF to avoid cancellation.
        fl_hpf = np.clip(self.hpf_cutoff * track_mult * vel_mult, 20.0, fl_lpf / 2.0)
        samples, hpf_s = self._filter_process(samples, fl_hpf, "hpf", hpf_s, 0.0)
        filtered, lpf_s = self._filter_process(samples, fl_lpf, "lpf", lpf_s, self.resonance)
        if rank == 1: voice.filter_state_lpf1, voice.filter_state_hpf1 = lpf_s, hpf_s
        else: voice.filter_state_lpf2, voice.filter_state_hpf2 = lpf_s, hpf_s
        return filtered

    def _apply_dc_blocker(self, voice: Voice, samples: np.ndarray) -> np.ndarray:
        xp, yp = voice.dc_blocker_x, voice.dc_blocker_y
        filtered = np.zeros_like(samples)
        for i in range(len(samples)):
            filtered[i] = samples[i] - xp + 0.999 * yp
            xp, yp = samples[i], filtered[i]
        voice.dc_blocker_x, voice.dc_blocker_y = xp, yp
        return filtered

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
                        if k == 'amp_level':       self.amp_level_target = v
                        elif k == 'master_volume': self.master_volume_target = v
                        else:                      setattr(self, k, v)
            elif e['type'] == 'all_notes_off':
                # Reset voices on the audio thread — safe between DSP buffers.
                for v in self.voices:
                    v.reset()
            else:
                # note_on / note_off — collect and process below with the cap.
                pending_notes.append(e)

        # Second pass: process note events with the 3-per-buffer cap.
        for e in pending_notes:
            if note_events_processed >= 3:
                # Re-enqueue remaining note events for the next buffer.
                self.midi_event_queue.put(e)
            else:
                if e['type'] == 'note_on':
                    self._trigger_note(e['note'], e['velocity'])
                    note_events_processed += 1
                elif e['type'] == 'note_off':
                    self._release_note(e['note'], e.get('velocity', 0.5))
                    note_events_processed += 1

    def _trigger_note(self, note: int, vel: float):
        freq = self._midi_to_frequency(note)
        for v in self.voices:
            if v.midi_note == note and v.note_active: v.trigger(note, freq, vel); return
        for v in self.voices:
            if v.is_available(): v.trigger(note, freq, vel); return
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
            best_v.dc_blocker_x = best_v.dc_blocker_y = 0.0
            best_v.trigger(note, freq, vel)

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
            lfo_val = np.sin(self.lfo_phase)
            self.lfo_phase = (self.lfo_phase + 2 * np.pi * self.lfo_freq * frame_count / self.sample_rate) % (2 * np.pi)
            vco_lfo = 1.0 + (lfo_val * self.lfo_vco_mod * 0.05)
            vcf_lfo = 1.0 + (lfo_val * self.lfo_vcf_mod * 0.5)
            vca_lfo = 1.0 + (lfo_val * self.lfo_vca_mod * 0.3)
            mixed_l = np.zeros(frame_count, dtype=np.float32)
            mixed_r = np.zeros(frame_count, dtype=np.float32)

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
                    s1 = self._apply_filter(v, s1, rank=1, cutoff_mod=vcf_lfo)
                    if self.rank2_enabled:
                        f2 = f1 * (2.0 ** (self.rank2_detune / 1200.0))
                        s2, v.phase2 = self._generate_waveform(self.rank2_waveform, f2, frame_count, p2_s)
                        s2 = self._apply_filter(v, s2, rank=2, cutoff_mod=vcf_lfo)
                        v_samples = s1 * (1.0 - self.rank2_mix) + s2 * self.rank2_mix
                    else:
                        v_samples = s1
                    if self.sine_mix > 0:
                        # Use and advance the voice's dedicated sine_phase accumulator
                        # so the sub-oscillator is phase-continuous across buffer boundaries.
                        ss, v.sine_phase = self._generate_waveform("pure_sine", f1, frame_count, v.sine_phase)
                        v_samples += ss * self.sine_mix
                    v_samples = self._apply_envelope(v, v_samples, frame_count) * vca_lfo
                    # Per-voice onset ramp: a short linear fade-in on the raw
                    # post-envelope signal before the DC blocker. The DC blocker
                    # resets to zero on every new trigger; if the signal is non-zero
                    # at sample 0 the blocker's first output is x[0]-0+0 = x[0],
                    # then x[1]-x[0]+... which differentiates a large first step
                    # into a high-frequency click. Fading in over the first
                    # ONSET_RAMP samples ensures the blocker starts from near-zero
                    # signal regardless of oscillator phase or attack setting.
                    ONSET_RAMP = int(self.sample_rate * 0.003)  # 3ms = ~144 samples
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
            # comp normalises waveform RMS to roughly the same perceived loudness.
            # Kept intentionally modest (≤1.0 for sine) so that at default amp_level
            # (0.75) and sustain (0.7) the pre-tanh drive stays below ~0.5 — well
            # inside tanh's linear region.  This prevents the attack transient from
            # saturating harder than the sustain, which was causing the visible
            # peak-then-sag shape in recorded waveforms.
            comp = 0.9 if self.waveform in ["sine", "pure_sine"] else (0.6 if self.waveform == "square" else 1.1)
            # master_volume scales drive into tanh (musical: lower vol = less saturation).
            # gain_ramp is applied per-sample before tanh so there are no step jumps.
            drive = self.amp_level_current * comp * self.master_volume
            # Post-tanh makeup gain restores output level to full-scale without
            # altering the shape of the tanh curve seen by the signal.
            makeup = 1.0 / max(np.tanh(drive * float(self.master_gain_current)), 0.01)
            mixed_l = np.tanh(mixed_l * drive * gain_ramp) * makeup
            mixed_r = np.tanh(mixed_r * drive * gain_ramp) * makeup
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
