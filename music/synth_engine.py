"""Synthesizer engine for generating audio waveforms."""
import os
import sys
import math
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
        self.velocity = 1.0  # Current smoothed velocity (used in envelope calculations)
        self.velocity_current = 1.0
        self.velocity_target = 1.0
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

        # FIR history buffers for polyphase oversampling: hold the last (N_taps-1)=30
        # oversampled samples from the previous buffer so convolution uses actual past
        # samples instead of zero-padding at buffer boundaries.  Zero-padding creates
        # systematic edge artefacts that become large at note transitions.
        # Separate buffers per oscillator rank so each rank's history is independent.
        self._oversample_history:      np.ndarray = np.zeros(30, dtype=np.float32)  # rank 1
        self._oversample_history_r2:   np.ndarray = np.zeros(30, dtype=np.float32)  # rank 2
        self._oversample_history_sine: np.ndarray = np.zeros(30, dtype=np.float32)  # sine sub

        # Last mono-mixed output sample from the most recent rendered buffer (after all
        # processing: FIR, envelope, onset ramp, DC blocker, pan/gain).  Updated every
        # buffer.  Used by the soft-trigger crossfade to ensure the FIRST sample of a new
        # buffer is identical to the LAST sample of the previous one, hiding FIR
        # boundary transients that arise when frequency changes at a note transition.
        self.last_output_sample: float = 0.0
        # Number of crossfade samples remaining from a soft-trigger transition.
        # The render loop blends from last_output_sample toward the new output over
        # this many samples (typically 4 = 1 audio sample per oversampled step).
        self.crossfade_samples: int = 0

        # Filter EG per-voice state — one-shot ADSR that modulates filter cutoff.
        # Resets on every note trigger; independent of the amp envelope lifecycle.
        self.feg_time:          float = 0.0    # elapsed time since last trigger
        self.feg_is_releasing:  bool  = False  # True after note-off
        self.feg_release_start: float = 0.0   # feg_time value at note-off (for t_rel)
        self.feg_release_level: float = 0.0   # actual FEG level captured at note-off

        # Pre-gate progress for MONO and UNISON voice modes.
        # Tracks linear 0→1 progress over 30ms after each note trigger; the actual
        # gate multiplier applied to the oscillator output is computed as an S-curve
        # (1 - cos(π·progress)) / 2 so both the start and end of the fade-in have
        # zero slope — no instantaneous amplitude steps at either endpoint.
        # Applied between oscillator and filter so the filter sees a smoothly growing
        # signal.  Default 1.0 = fully open; zero impact on all other paths.
        self.pre_gate_progress: float = 1.0

        # Per-voice filter cutoff smoothing: tracks the effective fl_lpf / fl_hpf used
        # in the previous buffer.  Interpolating toward the new value each buffer prevents
        # sudden coefficient jumps (from FEG restart, key-tracking note changes, or large
        # EG amounts) from creating state/coefficient mismatches that high-resonance filters
        # amplify into audible spikes.  -1.0 = uninitialised (set on first use).
        self.smooth_fl_lpf: float = -1.0
        self.smooth_fl_hpf: float = -1.0

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
        # Use velocity_target for smoothing; velocity_current will ramp toward it
        self.velocity_target = velocity
        self.note_active = True
        self.is_releasing = False
        self.envelope_time = 0.0
        self.age = 0.0
        self.onset_samples = 0   # restart the per-voice fade-in ramp
        self.onset_ms = 3.0      # reset to default; _trigger_note sets the real value
        # FEG restarts from zero on every new trigger
        self.feg_time = 0.0
        self.feg_is_releasing = False
        self.feg_release_start = 0.0

        # RESET filter/DC memory if starting from silence OR if this is a voice steal
        # (same voice being retaken by a different note). Preserving stale filter/DC
        # state from the stolen note would cause a DC sag at the start of the new note.
        if True:  # always reset — free-running phase is preserved, states are not
            self.filter_state_ladder1 = [0.0, 0.0, 0.0, 0.0]
            self.filter_state_ladder2 = [0.0, 0.0, 0.0, 0.0]
            self.filter_state_svf1_lp = self.filter_state_svf1_bp = 0.0
            self.filter_state_svf2_lp = self.filter_state_svf2_bp = 0.0
            self.dc_blocker_x = self.dc_blocker_y = 0.0
            # Note: self.phase and self.sine_phase are NOT reset here (Free-Running)
            # Clear FIR history only when starting from true silence.  For voice-steal
            # or legato transitions (was_silent=False), preserve history so the FIR
            # filter sees actual past samples and transitions smoothly from the old
            # frequency rather than jumping from zeros — zeroing history at a non-silent
            # transition is the primary cause of boundary-delta click artifacts.
            if was_silent:
                self._oversample_history[:] = 0.0
                self._oversample_history_r2[:] = 0.0
                self._oversample_history_sine[:] = 0.0

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
        self.filter_state_ladder1 = [0.0, 0.0, 0.0, 0.0]
        self.filter_state_ladder2 = [0.0, 0.0, 0.0, 0.0]
        self.filter_state_svf1_lp = self.filter_state_svf1_bp = 0.0
        self.filter_state_svf2_lp = self.filter_state_svf2_bp = 0.0
        self.dc_blocker_x = self.dc_blocker_y = 0.0
        self.last_envelope_level = 0.0
        self.sine_phase = 0.0
        self.onset_samples = 0
        self.feg_time = 0.0
        self.feg_is_releasing = False
        self.feg_release_start = 0.0
        self._oversample_history[:] = 0.0
        self._oversample_history_r2[:] = 0.0
        self._oversample_history_sine[:] = 0.0


class SynthEngine:
    """8-voice polyphonic synthesizer engine with stabilized gain and master volume."""

    def __init__(self):
        self.sample_rate = 48000
        self.buffer_size = 512
        self.num_voices = 8
        self.audio = None
        self.stream = None
        self.running = False

        self.waveform = "sine"
        self.octave = 0
        self.noise_level = 0.0
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
        self.intensity = 1.0  # Always 100% — removed from UI

        # Filter EG — per-voice one-shot ADSR that modulates LPF cutoff.
        # feg_amount=0.0 means fully bypassed; all existing presets default to this.
        # Maximum sweep: feg_amount × _FEG_MAX_SWEEP_HZ added to (or subtracted from) cutoff.
        self.feg_attack  = 0.01
        self.feg_decay   = 0.3
        self.feg_sustain = 0.0
        self.feg_release = 0.3
        self.feg_amount  = 0.0
        self._FEG_MAX_SWEEP_HZ = 8000.0  # maximum cutoff shift at amount=±1.0

        self.cutoff = 2000.0
        self.hpf_cutoff = 20.0
        self.resonance = 0.3
        self.hpf_resonance = 0.0      # 0.0–0.99 resonance (peak) for the HPF stage
        self.filter_mode = "ladder"   # kept for preset backward-compat; LPF always uses ladder now
        # SVF→Ladder routing: selects which SVF output feeds into the Moog ladder stage.
        # "lp_hp" = SVF HP → Ladder (MS-20 default), "bp_lp" = SVF BP → Ladder,
        # "notch_lp" = SVF Notch → Ladder, "lp_lp" = SVF LP → Ladder (dual LP).
        self.filter_routing = "lp_hp"

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

        # ── Pre-allocated audio callback buffers ─────────────────────────
        # All temporary arrays needed by _audio_callback are allocated here
        # at startup and reused in-place each callback. Zero malloc/free in
        # the hot path prevents GC-pause deadline misses that cause clicks.
        _bs = self.buffer_size
        self._cb_mixed_l  = np.zeros(_bs, dtype=np.float32)
        self._cb_mixed_r  = np.zeros(_bs, dtype=np.float32)
        self._cb_cho_l    = np.zeros(_bs, dtype=np.float32)
        self._cb_cho_r    = np.zeros(_bs, dtype=np.float32)
        self._cb_wet_l    = np.zeros(_bs, dtype=np.float32)
        self._cb_wet_r    = np.zeros(_bs, dtype=np.float32)
        self._cb_gain_ramp = np.zeros(_bs, dtype=np.float32)
        self._cb_out      = np.zeros(_bs * 2, dtype=np.int32)
        # Float index array reused for vectorized ring-buffer index math
        self._cb_indices  = np.arange(_bs, dtype=np.float32)

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

        self.amp_level = 0.95
        self.amp_level_target = 0.95
        self.amp_level_current = 0.95
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
        self.hpf_cutoff_current   = 20.0
        self.hpf_cutoff_target    = 20.0
        self.hpf_cutoff_smoothing = 0.85
        self.resonance_current   = 0.3
        self.resonance_target    = 0.3
        self.resonance_smoothing = 0.90
        self.hpf_resonance_current   = 0.0
        self.hpf_resonance_target    = 0.0
        self.hpf_resonance_smoothing = 0.90
        self.noise_level_current = 0.0
        self.noise_level_target  = 0.0
        self.noise_level_smoothing = 0.90
        self.key_tracking_current = 0.5
        self.key_tracking_target  = 0.5
        self.key_tracking_smoothing = 0.90
        self.filter_drive_current = 1.0   # pre-filter gain multiplier (0.5–8.0)
        self.filter_drive_target  = 1.0
        self.filter_drive_smoothing = 0.85
        self.voice_type = "poly"  # "mono", "poly", "unison"
        self.mono_voice_index = 0  # For mono mode, which voice to use (always self._mono_primary)
        self._mono_primary = 0    # Alternates between 0 and 1: active MONO voice slot
        self.unison_detune = 8.0   # Cents spread for unison mode (each voice detuned within ±unison_detune)
        self._held_notes_ordered: list = []  # Ordered note stack for MONO/UNISON last-note priority (list of (note, velocity))
        self._held_notes_vel: dict = {}      # note -> velocity (0-1) for last-note priority resume
        self.velocity_current = 1.0
        self.velocity_target = 1.0
        self.velocity_smoothing = 0.92  # Smooth velocity changes to prevent attack peaks

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
        # When True, the mute ramp will reset all voices at its bottom instead
        # of arming a fade-in. Used by soft_all_notes_off() for click-free mode switches.
        self._pending_all_notes_off = False

        # Engine-level inter-buffer crossfade: eliminates clicks when MONO/UNISON
        # note transitions change frequency mid-buffer.  The FIR downsampler sees a
        # frequency step which creates a 1-2 sample boundary transient.  We store the
        # last post-tanh output sample every buffer and, when a soft trigger has
        # occurred, cross-fade from those stored values toward the new output over
        # _TRANSITION_XF_SAMPLES samples at the start of the transition buffer.
        # Post-tanh storage guarantees exact amplitude continuity regardless of
        # drive / gain_ramp changes between buffers.
        self._last_output_L: float = 0.0
        self._last_output_R: float = 0.0
        self._transition_xf_remaining: int = 0  # samples left in active crossfade
        self._TRANSITION_XF_SAMPLES:  int = 8   # 8 smp ≈ 0.17ms: inaudible at 48kHz

        # FX tail drain counter — keeps the audio callback alive (not early-returning
        # silence) while Delay / Chorus ring buffers still have audible wet content.
        # Set to the maximum possible tail length (delay_max_seconds * feedback_decay)
        # whenever a note is triggered; decremented by frame_count each buffer when
        # active_count == 0.  0 means "no tail to drain — safe to output silence."
        # Max tail = 2s delay × ~10 echoes at 0.9 feedback ≈ 20s, but we cap at 10s
        # (480000 samples) to avoid infinite draining if feedback is maxed.
        self._fx_tail_samples = 0        # samples remaining to drain after all voices silent
        self._FX_TAIL_MAX     = int(self.sample_rate * 10.0)   # 10s ceiling

        # Startup silence counter — outputs zero samples for first ~1s after stream starts.
        # Eliminates click artifacts from filter/DC blocker transients during warm-up.
        # 1 second allows all DSP state (filters, DC blockers, LFO, arpeggiator) to fully settle.
        self._startup_silence_samples = int(self.sample_rate * 1.0)  # 1 second of silence

        self.pitch_bend = 0.0
        self.pitch_bend_target = 0.0
        self.pitch_bend_smoothing = 0.85
        self.mod_wheel = 0.0

        # ── Oversampling configuration (Phase 3) ──────────────────────────────
        # 4× internal oscillator oversampling for alias-free sawtooth/square/triangle
        self.OVERSAMPLE_FACTOR = 4              # Generate at 192 kHz, downsample to 48 kHz
        self.ENABLE_OVERSAMPLING = True         # Toggle for performance testing
        self.OVERSAMPLE_SAMPLE_RATE = 48000 * self.OVERSAMPLE_FACTOR  # 192 kHz
        self._downsample_filter_taps = None     # Pre-computed FIR filter (initialized below)

        self.voices: List[Voice] = [Voice(self.sample_rate, i) for i in range(self.num_voices)]
        self.held_notes: set = set()
        self.midi_event_queue = queue.Queue()

        # Initialize polyphase downsampling filter for oversampling
        self._create_polyphase_filter()

        if AUDIO_AVAILABLE and pyaudio is not None:
            try:
                self.audio = pyaudio.PyAudio()
                default_output = self.audio.get_default_output_device_info()
                self.stream = self.audio.open(
                    format=pyaudio.paInt24, channels=2, rate=self.sample_rate,
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

    def _create_polyphase_filter(self):
        """ABOUTME: Create 31-tap Hamming-windowed sinc FIR lowpass filter for 4× downsampling.
        ABOUTME: Cutoff at 20 kHz with > 60dB attenuation above Nyquist."""
        N = 31  # Tap count (odd for symmetry)
        n = np.arange(N) - N // 2  # Center at 0: [-15, -14, ..., 0, ..., 14, 15]

        # Normalized cutoff frequency: 20 kHz / (192000 Hz / 2) = 0.208
        # This ensures the filtered signal has no content above 20 kHz at 192 kHz sampling
        normalized_cutoff = 20000.0 / (192000.0 / 2.0)

        # Sinc function: sin(πx) / (πx), with special handling at x=0
        with np.errstate(divide='ignore', invalid='ignore'):
            h = np.sinc(2.0 * normalized_cutoff * n)
            h[N // 2] = 2.0 * normalized_cutoff  # Direct evaluation at x=0

        # Apply Hamming window to reduce Gibbs side-lobes
        window = np.hamming(N)
        h_windowed = h * window

        # Normalize so passband gain is ~1.0 at DC
        self._downsample_filter_taps = (h_windowed / np.sum(h_windowed)).astype(np.float32)

    def _downsample_polyphase_signal(self, oversampled: np.ndarray, downsample_factor: int = 4,
                                     history: np.ndarray = None) -> np.ndarray:
        """ABOUTME: Polyphase downsampling: convolve with lowpass filter, decimate by factor.
        ABOUTME: Input: oversampled array at 192 kHz, Output: decimated array at 48 kHz."""
        if not self.ENABLE_OVERSAMPLING or self._downsample_filter_taps is None:
            return oversampled[:len(oversampled) // downsample_factor]

        expected_len = len(oversampled) // downsample_factor
        n_taps = len(self._downsample_filter_taps)
        history_len = n_taps - 1   # 30 samples for a 31-tap filter

        if history is not None:
            # Prepend the caller-supplied FIR history so each buffer boundary uses
            # actual past samples instead of zero-padding.  mode='valid' produces
            # exactly len(oversampled) output samples with no edge artefacts.
            extended = np.concatenate([history, oversampled])
            filtered  = np.convolve(extended, self._downsample_filter_taps, mode='valid')
            # Update history in-place with the last history_len samples of THIS buffer
            history[:] = oversampled[-history_len:]
        else:
            # Fallback (no history supplied): original zero-padding behaviour
            filtered = np.convolve(oversampled, self._downsample_filter_taps, mode='same')

        # Decimate: take every Nth sample (phase 0 — indices 0, 4, 8, …)
        decimated = filtered[::downsample_factor]
        return decimated[:expected_len].astype(np.float32)

    def _generate_pink_noise(self, num_samples: int) -> np.ndarray:
        """ABOUTME: Generate pink noise using Voss-McCartney algorithm (fast vectorized).
        ABOUTME: Approximates 1/f spectrum with minimal CPU overhead."""
        # Initialize state buffers if needed
        if not hasattr(self, '_pink_state'):
            self._pink_state = np.zeros(7, dtype=np.float32)

        # Generate white noise
        white = np.random.randn(num_samples).astype(np.float32)

        # Fast vectorized pink noise: simple cascade of accumulators
        # This approximates pink noise with O(1) per-sample cost (vs expensive IIR)
        pink = np.zeros(num_samples, dtype=np.float32)
        state = self._pink_state.copy()

        # Use cascade of integrators with different decay rates for 1/f response
        for i in range(num_samples):
            # Add weighted white noise to each state variable
            state[0] = 0.99765 * state[0] + white[i] * 0.0990460
            state[1] = 0.96494 * state[1] + white[i] * 0.2965164
            state[2] = 0.57115 * state[2] + white[i] * 1.0526500

            # Mix states to create pink noise
            pink[i] = (state[0] + state[1] + state[2]) * 0.333333

        # Save state for next call (ensures spectral continuity)
        self._pink_state = state

        return pink.astype(np.float32)

    def _generate_waveform(self, waveform: str, frequency: float, num_samples: int, start_phase: float, oversample_factor: int = 1) -> tuple[np.ndarray, float]:
        # Handle noise waveforms first (they don't use frequency/phase)
        if waveform == "noise_white":
            samples = np.random.randn(num_samples).astype(np.float32) * 0.5
            return samples, start_phase
        elif waveform == "noise_pink":
            samples = self._generate_pink_noise(num_samples) * 0.5
            return samples, start_phase

        # Regular pitched waveforms use phase accumulation
        # Support 4× oversampling: generate at 192 kHz if oversample_factor=4
        effective_sample_rate = self.sample_rate * oversample_factor
        effective_num_samples = num_samples * oversample_factor

        phase_inc = 2 * np.pi * frequency / effective_sample_rate
        t = np.arange(effective_num_samples)
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
            # Sawtooth (default)
            samples = 2.0 * t_norm - 1.0

        # Apply PolyBLEP anti-aliasing to band-limited waveforms
        if waveform in ["sawtooth", "square", "triangle"]:
            samples = self._apply_polyblep(waveform, samples, phases, frequency, effective_num_samples, effective_sample_rate)

        final_phase = (start_phase + effective_num_samples * phase_inc) % (2 * np.pi)
        return samples.astype(np.float32), final_phase

    def _apply_polyblep(self, waveform: str, samples: np.ndarray, phase: np.ndarray, frequency: float, num_samples: int, sample_rate: float = None) -> np.ndarray:
        """Apply PolyBLEP (Polynomial BLEP) anti-aliasing correction to sawtooth, square, and triangle."""
        if sample_rate is None:
            sample_rate = self.sample_rate
        phase_inc = 2 * np.pi * frequency / sample_rate
        dphi = phase_inc / (2 * np.pi)  # Normalized phase increment

        # Normalized phase 0..1
        t_norm = (phase % (2 * np.pi)) / (2 * np.pi)

        if waveform == "sawtooth":
            # Apply PolyBLEP at the sawtooth discontinuity (every period at phase 0)
            # Rising edge correction near phase 0
            mask_rise = t_norm < dphi
            polyblep_rise = -0.5 * (t_norm[mask_rise] / dphi) ** 2 + t_norm[mask_rise] / dphi - 0.5
            samples[mask_rise] += polyblep_rise

            # Falling edge correction near phase 1 (2π)
            mask_fall = t_norm > (1.0 - dphi)
            polyblep_fall = 0.5 * ((1.0 - t_norm[mask_fall]) / dphi) ** 2 - (1.0 - t_norm[mask_fall]) / dphi + 0.5
            samples[mask_fall] += polyblep_fall
        elif waveform == "square":
            # Square wave has discontinuities at 0 and 0.5 (rising and falling edges)
            # Rising edge at 0
            mask_rise = t_norm < dphi
            polyblep_rise = -0.5 * (t_norm[mask_rise] / dphi) ** 2 + t_norm[mask_rise] / dphi - 0.5
            samples[mask_rise] += polyblep_rise

            # Falling edge at 0.5
            t_norm_half = (t_norm - 0.5) % 1.0
            mask_fall = t_norm_half < dphi
            polyblep_fall = 0.5 * ((t_norm_half[mask_fall]) / dphi) ** 2 - (t_norm_half[mask_fall]) / dphi - 0.5
            samples[mask_fall] -= polyblep_fall
        elif waveform == "triangle":
            # Triangle has discontinuities in its derivative at 0 and 0.5
            # Rising slope edge at 0
            mask_rise = t_norm < dphi
            polyblep_rise = -0.5 * (t_norm[mask_rise] / dphi) ** 2 + t_norm[mask_rise] / dphi - 0.5
            samples[mask_rise] += 2.0 * polyblep_rise  # Scale for steeper slopes

            # Falling slope edge at 0.5
            t_norm_half = (t_norm - 0.5) % 1.0
            mask_fall = t_norm_half < dphi
            polyblep_fall = 0.5 * ((t_norm_half[mask_fall]) / dphi) ** 2 - (t_norm_half[mask_fall]) / dphi - 0.5
            samples[mask_fall] -= 2.0 * polyblep_fall

        return samples

    def _apply_envelope(self, voice: Voice, samples: np.ndarray, num_samples: int) -> np.ndarray:
        dt = 1.0 / self.sample_rate
        VEL_C, VEL_F = 1.3, 0.15
        v_scaled = VEL_F + (1.0 - VEL_F) * (voice.velocity ** VEL_C)
        v_int = 1.0 * v_scaled
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
            # Use time_const (not self.release) for the safety timeout so that
            # soft note-off velocities (rel_mod > 1) don't cause an audible hard
            # cut before the exponential reaches inaudible levels.
            # 10 time constants → exp(-10) ≈ 0.00005, well below the 0.001 threshold.
            if envelope[-1] < 0.001 or times[-1] > time_const * 10: voice.reset()
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
            # DC blocker settling transient suppression is now handled by ONSET_RAMP
            # (frequency-adaptive linear fade-in applied to post-envelope signal).
            # Removed ANTI_I exponential envelope suppression to prevent interference
            # with the attack envelope and eliminate undesired dips at onset boundary.
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
        Alpha is capped at 0.95 to prevent IIR instability at high cutoff frequencies
        (alpha > 1.0 violates the stability condition of the discrete integrator).
        """
        sr = self.sample_rate
        fc = float(np.clip(cutoff, 20.0, sr * 0.45))
        alpha = float(np.clip(2.0 * np.pi * fc / sr, 0.0, 0.95))
        # k normalisation: resonance feedback scales down with alpha so the
        # filter remains unconditionally stable; k→1.0 approaches self-oscillation.
        # Scale by 1.2 for more aggressive resonance character
        k = float(np.clip(res * 1.2 * (1.0 / (1.0 + alpha)), 0.0, 0.99))

        N = len(samples)
        out = np.zeros(N, dtype=np.float32)
        s0, s1, s2, s3 = prev_states[0], prev_states[1], prev_states[2], prev_states[3]
        a1 = 1.0 - alpha

        for i in range(N):
            # Input saturated with global feedback from previous stage-4 output
            x0 = float(np.tanh(float(samples[i]) - 4.0 * k * s3))
            # Per-stage tanh saturation — each integrator clips softly like a real
            # Moog ladder transistor stage, producing even harmonics when driven.
            # math.tanh is used here (scalar) which is faster than np.tanh in a loop.
            s0 = math.tanh(a1 * s0 + alpha * x0)
            s1 = math.tanh(a1 * s1 + alpha * s0)
            s2 = math.tanh(a1 * s2 + alpha * s1)
            s3 = math.tanh(a1 * s3 + alpha * s2)
            out[i] = s3

        # Gain compensation: per-stage tanh reduces output level ~1-2 dB for clean signals.
        # Scale up to restore unity gain so mix levels remain stable when drive is at 1.0.
        out *= 1.1

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
        # More aggressive Q curve: higher resonance = higher Q (more pronounced peak)
        q = float(np.clip(0.5 + res * 10.0, 0.5, 10.5))

        N = len(samples)
        out = np.zeros(N, dtype=np.float32)
        lp = lp_state
        bp = bp_state

        for i in range(N):
            # Correct Chamberlin order: lp uses previous bp, bp uses current hp
            lp = lp + f * bp              # integrate bp → lp (previous bp)
            hp = float(samples[i]) - lp - q * bp
            bp = bp + f * hp              # integrate hp → bp
            # Soft tanh saturation — same limits as before but smooth analog character
            lp = math.tanh(lp * 0.25) * 4.0
            bp = math.tanh(bp * 0.25) * 4.0
            out[i] = lp

        return out, lp, bp

    def _filter_svf_hp_process(self, samples: np.ndarray, cutoff: float,
                               lp_state: float, bp_state: float,
                               res: float = 0.0, routing: str = "lp_hp") -> tuple:
        """Chamberlin SVF — multi-output.  Returns selected routing output plus integrator states.

        HPF cutoff capped at sr/12 (~4kHz) for Chamberlin stability, which covers
        the full useful HPF range (20Hz–4kHz).  Resonance q range is kept narrower
        than the LPF (0.5–4.0) to keep the HP peak well-behaved without runaway.

        routing selects which SVF output feeds the downstream Moog ladder stage:
          "lp_hp"   → HP output (MS-20 default — HPF into Ladder LPF)
          "bp_lp"   → BP output (band-limited signal into Ladder LPF)
          "notch_lp"→ Notch output (band-reject into Ladder LPF)
          "lp_lp"   → LP output (dual LP — very smooth/dark character)
        """
        sr = self.sample_rate
        fc = float(np.clip(cutoff, 20.0, sr / 12.0))
        f = float(np.clip(2.0 * np.sin(np.pi * fc / sr), 0.0, 0.5))
        # Narrower Q range for HPF: 0.5 (flat) → 4.0 (strong resonant peak)
        q = float(np.clip(0.5 + res * 3.5, 0.5, 4.0))

        N = len(samples)
        out = np.zeros(N, dtype=np.float32)
        lp = lp_state
        bp = bp_state

        for i in range(N):
            lp = lp + f * bp
            hp = float(samples[i]) - lp - q * bp
            bp = bp + f * hp
            # Soft tanh saturation — analog-style limiting, smoother than hard clamp
            lp = math.tanh(lp * 0.25) * 4.0
            bp = math.tanh(bp * 0.25) * 4.0
            # HP is bounded naturally by bp saturation; no separate clamp needed
            if routing == "lp_hp":
                out[i] = hp
            elif routing == "bp_lp":
                out[i] = bp
            elif routing == "notch_lp":
                out[i] = float(samples[i]) - lp  # notch = input - lp (Chamberlin formula)
            else:  # "lp_lp"
                out[i] = lp

        return out, lp, bp

    def _apply_filter(self, voice: Voice, samples: np.ndarray, rank: int = 1, cutoff_mod: float = 1.0) -> np.ndarray:
        """MS-20 style dual filter: resonant SVF HPF → Ladder LPF in series.

        HPF stage uses the Chamberlin SVF HP output — hpf_cutoff_current + hpf_resonance_current.
        LPF stage always uses the 4-pole Moog ladder — cutoff_current + resonance_current.
        Both stages are modulated by key tracking and velocity.
        Per-voice SVF integrator states (svf*_lp/bp) are repurposed for the HPF stage;
        the SVF slots are no longer used for the LPF since the ladder always handles that.
        """
        # Key tracking: shift cutoff proportionally with pitch relative to C4 (middle C).
        # C4 (261.63 Hz) is the reference — track_mult = 1.0 at C4 regardless of KT.
        # Formula: linear interpolation between 1.0 (no tracking) and f/261.63 (full tracking).
        f_base = voice.base_frequency or 261.63
        track_mult = 1.0 + self.key_tracking_current * (f_base / 261.63 - 1.0)

        fl_lpf = float(np.clip(self.cutoff_current * cutoff_mod * track_mult, 20.0, 20000.0))
        fl_hpf = float(np.clip(self.hpf_cutoff_current * track_mult, 20.0, fl_lpf * 0.9))

        # Per-voice coefficient smoothing: interpolate from previous buffer's value to the
        # new target.  Sudden jumps (FEG restart, key-tracking note change, high EG amount)
        # would otherwise create a state/coefficient mismatch that high-resonance filters
        # amplify into audible spikes.  Coefficient 0.65 → reaches ~94% of a step change
        # within ~6 buffers (~63ms) — still responsive enough to track LFO/EG sweeps
        # without perceptible lag, but slow enough to protect high-Q filters (k≈0.77,
        # feedback≈3.1) from state/coefficient mismatch transients.
        # This smoothing is intentionally preserved on MONO/UNISON legato note changes:
        # snapping the coefficient while the filter has stored resonant energy causes
        # the same spike it is designed to prevent.  The few-buffer lag is imperceptible
        # in musical legato playing and is preferable to a resonant click.
        _SMOOTH_K = 0.65
        if voice.smooth_fl_lpf < 0.0:   # first use: initialise to current value
            voice.smooth_fl_lpf = fl_lpf
            voice.smooth_fl_hpf = fl_hpf
        else:
            voice.smooth_fl_lpf = voice.smooth_fl_lpf * _SMOOTH_K + fl_lpf * (1.0 - _SMOOTH_K)
            voice.smooth_fl_hpf = voice.smooth_fl_hpf * _SMOOTH_K + fl_hpf * (1.0 - _SMOOTH_K)
        fl_lpf = voice.smooth_fl_lpf
        fl_hpf = voice.smooth_fl_hpf

        # ── HPF stage: resonant Chamberlin SVF (HP output) ───────────────────
        # Reuses the per-voice svf state slots (previously for LPF-SVF mode).
        hpf_lp_s = voice.filter_state_svf1_lp if rank == 1 else voice.filter_state_svf2_lp
        hpf_bp_s = voice.filter_state_svf1_bp if rank == 1 else voice.filter_state_svf2_bp
        samples, hpf_lp_s, hpf_bp_s = self._filter_svf_hp_process(
            samples, fl_hpf, hpf_lp_s, hpf_bp_s, self.hpf_resonance_current,
            routing=self.filter_routing)
        if rank == 1:
            voice.filter_state_svf1_lp, voice.filter_state_svf1_bp = hpf_lp_s, hpf_bp_s
        else:
            voice.filter_state_svf2_lp, voice.filter_state_svf2_bp = hpf_lp_s, hpf_bp_s

        # ── LPF stage: 4-pole Moog ladder (always) ───────────────────────────

        # Filter drive: pre-filter gain multiplier. Hitting the ladder stages harder
        # drives the per-stage tanh saturation, producing harmonic richness and warmth.
        if self.filter_drive_current != 1.0:
            samples = samples * self.filter_drive_current

        # Thermal noise floor — ~-100 dBFS (amplitude 1e-5), inaudible in isolation
        # but prevents filter dead-zone lock when self-oscillating at max resonance,
        # and adds a subtle analog "air" that's felt rather than heard in the mix.
        samples = samples + np.random.randn(len(samples)).astype(np.float32) * 1e-5

        ladder_s = voice.filter_state_ladder1 if rank == 1 else voice.filter_state_ladder2
        filtered, ladder_s = self._filter_ladder_process(
            samples, fl_lpf, ladder_s, self.resonance_current)
        if rank == 1: voice.filter_state_ladder1 = ladder_s
        else:         voice.filter_state_ladder2 = ladder_s

        return filtered

    def _feg_level_snapshot(self, voice: Voice) -> float:
        """Return the current FEG level without advancing feg_time (no side effects).

        Used to capture the exact level at note-off so feg_release_level is correct
        regardless of which ADSR phase the FEG was in (attack, decay, or sustain=0).
        """
        t = voice.feg_time
        if voice.feg_is_releasing:
            t_rel = max(0.0, t - voice.feg_release_start)
            return float(np.clip(voice.feg_release_level * np.exp(-t_rel / max(0.001, self.feg_release)), 0.0, 1.0))
        atk = max(0.001, self.feg_attack)
        dcy = max(0.001, self.feg_decay)
        sus = float(np.clip(self.feg_sustain, 0.0, 1.0))
        if t < atk:
            return float(t / atk)
        elif t < atk + dcy:
            return float(1.0 - ((t - atk) / dcy) * (1.0 - sus))
        return sus

    def _compute_feg_value(self, voice: Voice, num_samples: int) -> float:
        """Compute the Filter EG scalar (0.0–1.0) for the current buffer.

        Returns a single representative value for the buffer rather than a
        per-sample array — consistent with the per-buffer approach used for
        cutoff/resonance smoothing throughout the engine.  Fast-path returns
        0.0 immediately when feg_amount==0.0 so existing presets pay zero cost.
        """
        if self.feg_amount == 0.0:
            return 0.0

        dt = num_samples / self.sample_rate
        t = voice.feg_time

        if voice.feg_is_releasing:
            # Exponential release from feg_release_level (the actual level at note-off).
            # Decaying from 1.0 unconditionally was wrong: if the FEG had already reached
            # sustain=0% before key release, the release would jump to 1.0 then decay —
            # a sudden large cutoff step that high-resonance filters amplify into a spike.
            t_rel = max(0.0, t - voice.feg_release_start)
            time_const = max(0.001, self.feg_release)
            level = voice.feg_release_level * np.exp(-t_rel / time_const)
            voice.feg_time += dt
            return float(np.clip(level, 0.0, 1.0))
        else:
            # Attack → Decay → Sustain
            atk = max(0.001, self.feg_attack)
            dcy = max(0.001, self.feg_decay)
            sus = float(np.clip(self.feg_sustain, 0.0, 1.0))
            if t < atk:
                level = t / atk
            elif t < atk + dcy:
                p = (t - atk) / dcy
                level = 1.0 - p * (1.0 - sus)
            else:
                level = sus
            voice.feg_time += dt
            return float(np.clip(level, 0.0, 1.0))

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
                        if k == 'amp_level':         self.amp_level_target       = v
                        elif k == 'master_volume':   self.master_volume_target   = v
                        elif k == 'cutoff':          self.cutoff_target          = v
                        elif k == 'hpf_cutoff':      self.hpf_cutoff_target      = v
                        elif k == 'resonance':       self.resonance_target       = v
                        elif k == 'hpf_resonance':   self.hpf_resonance_target   = v
                        elif k == 'noise_level':     self.noise_level_target     = v
                        elif k == 'key_tracking':    self.key_tracking_target    = v
                        elif k == 'filter_drive':    self.filter_drive_target    = float(v)
                        elif k == 'filter_routing':  self.filter_routing         = v
                        elif k == 'feg_attack':      self.feg_attack  = float(v)
                        elif k == 'feg_decay':       self.feg_decay   = float(v)
                        elif k == 'feg_sustain':     self.feg_sustain = float(v)
                        elif k == 'feg_release':     self.feg_release = float(v)
                        elif k == 'feg_amount':      self.feg_amount  = float(v)
                        elif k == 'voice_type':      self.voice_type             = v
                        elif k == 'filter_mode':     pass  # kept for preset backward-compat; ignored
                        else:
                            setattr(self, k, v)
                            if k == 'delay_time':
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
                # Reset MONO dissolve state so next note starts clean on slot 0.
                self._mono_primary = 0; self.mono_voice_index = 0
                # Stop FX tail drain immediately — panic/all_notes_off means silence NOW.
                self._fx_tail_samples = 0
                self._pending_all_notes_off = False  # cancel any pending soft silence
            elif e['type'] == 'soft_all_notes_off':
                # Arm the mute ramp for a click-free 8ms fade-out, then reset all
                # voices at the bottom. Used during mode switches so notes release
                # smoothly instead of hard-cutting. No fade-in follows.
                self._mute_ramp_remaining = self._MUTE_RAMP_LEN
                self._mute_ramp_fadein    = 0
                self._pending_all_notes_off = True
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
        # drum_trigger events bypass the cap and are always processed immediately
        # so that all drums on a sequencer step fire in the same buffer.
        for e in pending_notes:
            if e['type'] == 'drum_trigger':
                # Atomic drum trigger: apply this drum's params then immediately
                # trigger its note. No cap — up to 8 drums can fire per buffer.
                self._apply_drum_params_inline(e['params'])
                self._trigger_note(e['note'], e['velocity'] / 127.0)
                note_events_processed += 1
                continue
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

    def _apply_drum_params_inline(self, params: dict):
        """Apply drum synthesis parameters directly on the audio thread (no smoothing queue).

        Called from the drum_trigger event handler in _process_midi_events() so that
        params and their note_on are always atomically paired. Smoothed params
        (cutoff, resonance, noise_level) are snapped to their target immediately
        rather than interpolated — percussive hits are short enough that smoothing
        provides no benefit and only causes bleed between simultaneous drums.
        """
        for k, v in params.items():
            if k == 'cutoff':
                self.cutoff_target = v
                self.cutoff_current = v
            elif k == 'resonance':
                self.resonance_target = v
                self.resonance_current = v
            elif k == 'noise_level':
                self.noise_level_target = v
                self.noise_level_current = v
            elif k == 'amp_level':
                self.amp_level_target = v
                self.amp_level_current = v
            elif k == 'filter_mode':
                pass  # LPF always uses ladder; filter_mode kept for preset compat only
            elif hasattr(self, k):
                setattr(self, k, v)

    def _trigger_note(self, note: int, vel: float):
        freq = self._midi_to_frequency(note)
        # Frequency-adaptive onset window: scale with the note period so the DC
        # blocker's startup transient is hidden under the onset ramp even for very
        # low notes.  Formula: 1.5 × period_ms, clamped [3ms, 30ms].
        # Examples: 440 Hz → 3ms (unchanged); 110 Hz → 13.5ms; 55 Hz → 27ms.
        period_ms = (1000.0 / freq) if freq > 0 else 3.0
        onset_ms_for_note = max(3.0, min(30.0, period_ms * 1.5))

        # Arm the FX tail drain counter so the audio callback continues processing
        # Delay and Chorus ring buffers even after all voices finish their release
        # envelope.  The value is set to _FX_TAIL_MAX (10s) here and decremented
        # in _audio_callback when active_count==0; it stops the early-return-to-
        # silence guard from firing while the delay echo or chorus tail is still
        # audible.  Setting it on EVERY note_on ensures re-trigger after silence
        # arms fresh headroom for the FX tail.
        self._fx_tail_samples = self._FX_TAIL_MAX

        if self.voice_type == "mono":
            # MONO with ADSR-overlap note dissolve.
            # Two voice slots (indices 0 and 1) alternate as primary/outgoing.
            # When a new note arrives while the current voice has amplitude, the
            # outgoing voice is put into release and the incoming voice is triggered
            # fresh.  Both voices play simultaneously during release/attack, producing
            # a natural cross-dissolve identical in character to the Compendium chord
            # transition.  When the note arrives from silence, a single hard trigger
            # fires with no crossfade needed.
            old_idx = self._mono_primary
            new_idx = 1 - self._mono_primary
            old_v = self.voices[old_idx]
            new_v = self.voices[new_idx]

            # Silence any voices outside the MONO pair (should never be active, but guard).
            for i, v in enumerate(self.voices):
                if i != old_idx and i != new_idx:
                    v.release(self.attack, self.decay, self.sustain, 1.0)

            has_amplitude = old_v.last_envelope_level > 0.001
            if has_amplitude:
                # Dissolve: send outgoing voice into ADSR release (it fades naturally),
                # trigger incoming voice from zero (it attacks naturally).
                # The overlap duration is the outgoing release time, so the crossfade
                # length is musically tied to the preset's release setting.
                old_v.release(self.attack, self.decay, self.sustain, 1.0)
                old_v.feg_release_level = self._feg_level_snapshot(old_v)
                old_v.feg_is_releasing = True
                old_v.feg_release_start = old_v.feg_time
                new_v.trigger(note, freq, vel)
                new_v.onset_ms = onset_ms_for_note
                new_v.phase = 0.0
                new_v.pre_gate_progress = 0.0
                self._mono_primary = new_idx
                self.mono_voice_index = new_idx
                # Short engine crossfade to hide any FIR transient at the transition boundary.
                self._transition_xf_remaining = self._TRANSITION_XF_SAMPLES
            else:
                # From silence: hard trigger on the primary slot, no crossfade needed.
                old_v.trigger(note, freq, vel)
                old_v.onset_ms = onset_ms_for_note
                old_v.phase = 0.0
                old_v.pre_gate_progress = 0.0

        elif self.voice_type == "unison":
            # Unison mode: all voices play same note with detuning spread.
            # Voices are detuned across ±unison_detune cents for the characteristic thick sound.
            n = len(self.voices)
            for i, v in enumerate(self.voices):
                # Spread voices evenly from -unison_detune to +unison_detune cents
                if n > 1:
                    detune_cents = self.unison_detune * (2.0 * i / (n - 1) - 1.0)
                else:
                    detune_cents = 0.0
                detuned_freq = freq * (2.0 ** (detune_cents / 1200.0))

                # Soft trigger whenever voice has amplitude (playing OR releasing).
                # A voice that just entered release this buffer still has amplitude —
                # hard trigger would drop it to 0 next sample → click.
                if v.last_envelope_level > 0.001:
                    # True legato: same reasoning as MONO soft trigger.
                    # Envelope continues from its current position — no attack restart,
                    # no steal crossfade.  Each detuned UNISON voice stays at its current
                    # level and phase.  The phase offset between voices created by their
                    # individual detuning frequencies produces the characteristic UNISON
                    # "swell" on legato — this beating is musically desirable and is the
                    # hallmark of a thick UNISON sound.  Do NOT reset phases here.
                    v.midi_note = note
                    v.base_frequency = detuned_freq
                    v.frequency = detuned_freq
                    v.velocity_target = vel
                    v.note_active = True
                    v.is_releasing = False
                    v.age = 0.0
                    v.onset_ms = onset_ms_for_note
                    # Arm engine-level crossfade (same as MONO).
                    self._transition_xf_remaining = self._TRANSITION_XF_SAMPLES
                    # Phase, pre_gate_progress, feg_time, and envelope_time are NOT reset.
                    # Resetting feg_time causes a sudden filter coefficient jump while
                    # the filter has stored energy — with high resonance this creates a
                    # spike.  Resetting phase + pre_gate creates a 30ms window where the
                    # filter resonates freely with no input, then interference spikes when
                    # the new signal re-enters.  Keeping all four continuous eliminates
                    # both spike sources and the double-attack dip.
                else:
                    # Hard trigger from true silence: full reset
                    v.trigger(note, detuned_freq, vel)
                    # Reset phase and open S-curve pre-gate for all waveforms.
                    v.phase = 0.0
                    v.pre_gate_progress = 0.0
                    v.onset_ms = onset_ms_for_note

        else:  # "poly" mode (default)
            # Retrigger if already playing
            for v in self.voices:
                if v.midi_note == note and v.note_active:
                    v.trigger(note, freq, vel)
                    v.onset_ms = onset_ms_for_note
                    return
            # Find available voice
            for v in self.voices:
                if v.is_available():
                    v.trigger(note, freq, vel)
                    v.onset_ms = onset_ms_for_note
                    return
            # Voice stealing: find "least important" voice based on priority
            best_v, best_p, best_s = None, -1, -1.0
            for v in self.voices:
                p = 2 if (v.is_releasing and v.midi_note not in self.held_notes) else (1 if v.is_releasing else 0)
                s = v.envelope_time if v.is_releasing else v.age
                if p > best_p or (p == best_p and s > best_s): best_p, best_s, best_v = p, s, v
            if best_v:
                # Zero ALL filter and DC blocker states before triggering so the new
                # note's frequency doesn't collide with stale filter memory from the
                # stolen note. The CROSS envelope crossfade in _apply_envelope handles
                # amplitude continuity, while this prevents a frequency-domain glitch
                # in the first few filter output samples.
                # Ladder (4-pole Moog LPF) integrators — must clear both ranks.
                best_v.filter_state_ladder1 = [0.0, 0.0, 0.0, 0.0]
                best_v.filter_state_ladder2 = [0.0, 0.0, 0.0, 0.0]
                # SVF (Chamberlin HPF) integrators — must clear both ranks.
                # Residual energy here creates a resonant spike on the stolen voice's
                # first buffer at high HPF resonance values.
                best_v.filter_state_svf1_lp = best_v.filter_state_svf1_bp = 0.0
                best_v.filter_state_svf2_lp = best_v.filter_state_svf2_bp = 0.0
                best_v.dc_blocker_x = best_v.dc_blocker_y = 0.0
                best_v.trigger(note, freq, vel)
                best_v.onset_ms = onset_ms_for_note
                # Stolen voice was already past its onset period — skip the onset_ramp.
                # onset_ramp + steal_start_level both fading in simultaneously creates a
                # double-damped attack (audible stutter gap). Only one mechanism should
                # handle the transition; steal_start_level (8ms CROSS crossfade) does it.
                best_v.onset_samples = int(self.sample_rate * onset_ms_for_note / 1000.0) + 1

    def _release_note(self, note: int, velocity: float = 0.5):
        if self.voice_type == "mono":
            # Last-note priority: if other notes are still held, resume the most recently pressed one.
            # held_notes is already updated (note removed) by the time this is called from the queue.
            remaining = [n for n in self._held_notes_ordered if n in self.held_notes]
            if remaining:
                resume_note = remaining[-1]
                resume_vel = self._held_notes_vel.get(resume_note, velocity)
                self._trigger_note(resume_note, resume_vel)
            else:
                mono_v = self.voices[self.mono_voice_index]
                if mono_v.note_active:
                    mono_v.release(self.attack, self.decay, self.sustain, 1.0, velocity)
                    mono_v.feg_release_level = self._feg_level_snapshot(mono_v)
                    mono_v.feg_is_releasing = True
                    mono_v.feg_release_start = mono_v.feg_time
        elif self.voice_type == "unison":
            # Last-note priority for unison: same logic but all 8 detuned voices.
            remaining = [n for n in self._held_notes_ordered if n in self.held_notes]
            if remaining:
                resume_note = remaining[-1]
                resume_vel = self._held_notes_vel.get(resume_note, velocity)
                self._trigger_note(resume_note, resume_vel)
            else:
                for v in self.voices:
                    if v.note_active:
                        v.release(self.attack, self.decay, self.sustain, 1.0, velocity)
                        v.feg_release_level = self._feg_level_snapshot(v)
                        v.feg_is_releasing = True
                        v.feg_release_start = v.feg_time
        else:
            for v in self.voices:
                if v.midi_note == note and v.note_active:
                    v.release(self.attack, self.decay, self.sustain, 1.0, velocity)
                    v.feg_release_level = self._feg_level_snapshot(v)
                    v.feg_is_releasing = True
                    v.feg_release_start = v.feg_time

    def _audio_callback(self, in_data, frame_count, time_info, status):
        try:
            # Output initial silence for ~50ms after startup to avoid filter transients
            if self._startup_silence_samples > 0:
                silence = bytes(frame_count * 2 * 3)  # 3 bytes per sample × 2 channels
                self._startup_silence_samples -= frame_count
                return (silence, pyaudio.paContinue)

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
            if abs(self.noise_level_current - self.noise_level_target) > 0.001:
                self.noise_level_current = (self.noise_level_current * self.noise_level_smoothing
                                            + self.noise_level_target * (1.0 - self.noise_level_smoothing))
            else:
                self.noise_level_current = self.noise_level_target
            if abs(self.key_tracking_current - self.key_tracking_target) > 0.001:
                self.key_tracking_current = (self.key_tracking_current * self.key_tracking_smoothing
                                             + self.key_tracking_target * (1.0 - self.key_tracking_smoothing))
            else:
                self.key_tracking_current = self.key_tracking_target
            if abs(self.hpf_cutoff_current - self.hpf_cutoff_target) > 0.5:
                self.hpf_cutoff_current = (self.hpf_cutoff_current * self.hpf_cutoff_smoothing
                                           + self.hpf_cutoff_target * (1.0 - self.hpf_cutoff_smoothing))
            else:
                self.hpf_cutoff_current = self.hpf_cutoff_target
            if abs(self.hpf_resonance_current - self.hpf_resonance_target) > 0.001:
                self.hpf_resonance_current = (self.hpf_resonance_current * self.hpf_resonance_smoothing
                                              + self.hpf_resonance_target * (1.0 - self.hpf_resonance_smoothing))
            else:
                self.hpf_resonance_current = self.hpf_resonance_target
            if abs(self.filter_drive_current - self.filter_drive_target) > 0.001:
                self.filter_drive_current = (self.filter_drive_current * self.filter_drive_smoothing
                                             + self.filter_drive_target * (1.0 - self.filter_drive_smoothing))
            else:
                self.filter_drive_current = self.filter_drive_target

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

            # Use pre-allocated buffers — fill with zeros in-place (no malloc)
            mixed_l = self._cb_mixed_l[:frame_count]
            mixed_r = self._cb_mixed_r[:frame_count]
            mixed_l.fill(0.0)
            mixed_r.fill(0.0)

            # ── Arpeggiator clock (audio-thread driven, sample-accurate) ────
            # The counter advances by frame_count each buffer; when it reaches
            # a step boundary we trigger the next note in the sequence and
            # release the previous one at the gate boundary.  The remainder is
            # carried over so the beat grid drifts by at most 1 sample over
            # any number of steps (no cumulative phase error from integer
            # rounding).
            if self.arp_enabled and self._arp_sequence:
                self._arp_sample_counter += frame_count
                # Gate-off: release the playing note once the gate window expires.
                # Known edge case: if gate_samples ≈ step_samples (gate ≈ 100%),
                # gate-off and step-trigger can fire in the same buffer.  This is
                # extremely rare at normal gate values and not worth the complexity
                # of a fix — the release transient is masked by the new note's attack.
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

                # FX tail drain: if Delay or Chorus are active and their ring buffers
                # still contain audible wet content, we must NOT early-return here.
                # Returning silence at this point would cut off the delay/chorus tails
                # even though the ring buffers still hold the echo/reverb signal.
                # Instead we fall through with mixed_l/mixed_r = zero — the voice loop
                # below produces nothing, but the Chorus and Delay DSP blocks will read
                # from their ring buffers and output the remaining wet tails naturally.
                # _fx_tail_samples is set to a generous ceiling whenever a voice is
                # triggered (in _trigger_note) and decremented here while draining so
                # the callback returns to silence naturally once the tail expires.
                if self._fx_tail_samples <= 0:
                    # Silence: 3 bytes per sample × 2 channels × frame_count frames
                    return (bytes(frame_count * 2 * 3), pyaudio.paContinue)
                self._fx_tail_samples = max(0, self._fx_tail_samples - frame_count)
                # Fall through: voices produce silence, FX blocks drain their buffers.

            # MONO voice count is always treated as 1 for gain purposes: during a
            # note dissolve two voices are briefly active (outgoing release + incoming
            # attack), but their combined amplitude is approximately constant so no
            # gain compensation is needed.  Applying 1/sqrt(2) here would cause an
            # audible volume dip in the middle of every MONO note transition.
            # UNISON mode also uses fixed gain=1.0: all 8 voices are always active
            # and already normalized by per-voice scaling (mix_scale = 1/num_voices).
            # Applying gain_ramp here would cause double attenuation (per-voice 1/8 × gain 0.354).
            gain_count = 1 if self.voice_type in ("mono", "unison") else active_count
            self.master_gain_target = 1.0 / np.sqrt(gain_count) if gain_count > 1 else 1.0
            # Snapshot gain AFTER the target is known but BEFORE smoothing,
            # so gain_ramp interpolates from the previous buffer's settled value
            # to the new smoothed value — a true per-sample continuous transition.
            gain_prev = self.master_gain_current
            # Faster coefficient (0.80) so the gain tracks voice-count changes
            # within ~2 buffers (~10ms) rather than drifting for 50ms+.
            self.master_gain_current = self.master_gain_current * 0.80 + self.master_gain_target * 0.20
            # Per-sample gain ramp: eliminates the buffer-boundary step discontinuity
            # that caused clicks when active_count changed between buffers.
            # Built from pre-allocated buffers — no malloc in the hot path.
            gain_ramp = self._cb_gain_ramp[:frame_count]
            _gr_step = (self.master_gain_current - gain_prev) / max(1, frame_count - 1)
            np.multiply(self._cb_indices[:frame_count], _gr_step, out=gain_ramp)
            gain_ramp += gain_prev

            for v in self.voices:
                if v.note_active or v.is_releasing:
                    # Smooth velocity to prevent attack peaks when notes change
                    if abs(v.velocity_current - v.velocity_target) > 0.001:
                        v.velocity_current = (v.velocity_current * self.velocity_smoothing
                                            + v.velocity_target * (1.0 - self.velocity_smoothing))
                    else:
                        v.velocity_current = v.velocity_target
                    v.velocity = v.velocity_current  # Update the velocity used in envelope/filter calculations

                    p1_s, p2_s = v.phase, v.phase2
                    f1 = v.frequency * vco_lfo if v.frequency else 440.0
                    if self.octave_enabled and self.octave != 0: f1 *= (2.0 ** self.octave)

                    # Generate primary oscillator with optional 4× oversampling
                    oversample_factor = self.OVERSAMPLE_FACTOR if self.ENABLE_OVERSAMPLING else 1
                    s1, v.phase = self._generate_waveform(self.waveform, f1, frame_count, p1_s, oversample_factor=oversample_factor)

                    # Downsample oscillator output from 192 kHz to 48 kHz if oversampling enabled.
                    # Noise waveforms skip oversampling in _generate_waveform (they return
                    # frame_count samples, not frame_count * oversample_factor), so only
                    # downsample when the signal is actually at the oversampled length.
                    if self.ENABLE_OVERSAMPLING and len(s1) == frame_count * oversample_factor:
                        s1 = self._downsample_polyphase_signal(s1, self.OVERSAMPLE_FACTOR, history=v._oversample_history)

                    # Pre-gate: S-curve fade-in over 10ms for sine/pure_sine in MONO/UNISON.
                    # Applied between oscillator and filter so the filter sees a smoothly
                    # growing signal from phase=0.  Shape: (1 - cos(π·t)) / 2 gives zero
                    # slope at both endpoints — no instantaneous amplitude steps at start
                    # or finish.  The existing steal crossfade (steal_start_level) handles
                    # fading out the old note's amplitude in parallel, creating a natural
                    # sequential out→in transition.  Default progress=1.0 = no effect.
                    if (self.voice_type in ("mono", "unison")
                            and v.pre_gate_progress < 1.0):
                        _GATE_RAMP_S = 0.030 * self.sample_rate  # 30ms in samples
                        _rate = 1.0 / _GATE_RAMP_S
                        _prog_start = v.pre_gate_progress
                        _prog_end = min(1.0, _prog_start + _rate * frame_count)
                        _prog_arr = np.linspace(_prog_start, _prog_end, frame_count, dtype=np.float32)
                        _prog_arr = np.clip(_prog_arr, 0.0, 1.0)
                        # S-curve: zero slope at 0 and 1, smooth throughout
                        _gate = ((1.0 - np.cos(np.pi * _prog_arr)) * 0.5).astype(np.float32)
                        v.pre_gate_progress = _prog_end
                        s1 = s1 * _gate

                    # Sine sub-oscillator mixed pre-filter so it's shaped by the
                    # filter (and Filter EG) alongside the primary oscillator.
                    if self.sine_mix > 0:
                        ss, v.sine_phase = self._generate_waveform("pure_sine", f1, frame_count, v.sine_phase, oversample_factor=oversample_factor)
                        if self.ENABLE_OVERSAMPLING and len(ss) == frame_count * oversample_factor:
                            ss = self._downsample_polyphase_signal(ss, self.OVERSAMPLE_FACTOR, history=v._oversample_history_sine)
                        s1 = s1 + ss * self.sine_mix

                    # Filter EG: compute per-buffer scalar and add to vcf_lfo modulation.
                    # feg_value is 0→1; scaled by feg_amount×_FEG_MAX_SWEEP_HZ and added
                    # to the base cutoff inside _apply_filter via cutoff_mod offset.
                    # When feg_amount==0.0 _compute_feg_value fast-paths to 0.0 with no overhead.
                    feg_val = self._compute_feg_value(v, frame_count)
                    feg_cutoff_offset = self.feg_amount * self._FEG_MAX_SWEEP_HZ * feg_val
                    # Pass as a combined modulator: vcf_lfo handles LFO ratio, FEG adds Hz offset.
                    # _apply_filter receives cutoff_mod as a multiplier; we encode the offset by
                    # adjusting the target cutoff temporarily per-voice via a local variable.
                    _base_cutoff = self.cutoff_current
                    self.cutoff_current = float(np.clip(_base_cutoff + feg_cutoff_offset, 20.0, 20000.0))
                    s1 = self._sanitize_signal(self._apply_filter(v, s1, rank=1, cutoff_mod=vcf_lfo))
                    self.cutoff_current = _base_cutoff  # restore immediately after filter call

                    if self.rank2_enabled:
                        f2 = f1 * (2.0 ** (self.rank2_detune / 1200.0))
                        s2, v.phase2 = self._generate_waveform(self.rank2_waveform, f2, frame_count, p2_s, oversample_factor=oversample_factor)

                        # Downsample rank 2 oscillator output if oversampling enabled.
                        # Guard length: noise waveforms return frame_count samples, not oversampled.
                        if self.ENABLE_OVERSAMPLING and len(s2) == frame_count * oversample_factor:
                            s2 = self._downsample_polyphase_signal(s2, self.OVERSAMPLE_FACTOR, history=v._oversample_history_r2)

                        self.cutoff_current = float(np.clip(_base_cutoff + feg_cutoff_offset, 20.0, 20000.0))
                        s2 = self._sanitize_signal(self._apply_filter(v, s2, rank=2, cutoff_mod=vcf_lfo))
                        self.cutoff_current = _base_cutoff
                        v_samples = s1 * (1.0 - self.rank2_mix) + s2 * self.rank2_mix
                    else:
                        v_samples = s1

                    if self.noise_level_current > 0:
                        # Blend full-spectrum white noise with the oscillator output.
                        # Noise is intentionally mixed post-FIR at 48 kHz rather than
                        # generated at 192 kHz and downsampled.  Full-bandwidth noise
                        # has more grit and textural character (analog-like air), whereas
                        # downsampling it through the FIR would over-smooth and sterilise
                        # the noise floor.  This is a deliberate character choice.
                        noise_sample = np.random.uniform(-1, 1, frame_count)
                        v_samples = v_samples * (1.0 - self.noise_level_current) + noise_sample * self.noise_level_current
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
                    # In UNISON mode all 8 voices sum simultaneously; scale each by 1/N
                    # so the total stays within tanh's linear region.  Without scaling,
                    # 8 voices saturate tanh and beat-pattern phase-resets on note
                    # transitions create large amplitude jumps at buffer boundaries.
                    mix_scale = (1.0 / self.num_voices) if self.voice_type == "unison" else 1.0
                    mixed_l += v_samples * np.cos(ang) * mix_scale
                    mixed_r += v_samples * np.sin(ang) * mix_scale
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
                # Vectorized chorus: compute all frame_count write/read positions
                # at once using numpy array ops instead of a Python per-sample loop.
                # Replaces O(frame_count × n_voices) Python iterations with BLAS-level
                # numpy calls; at 256 samples × 4 voices this eliminates ~1024
                # Python-level loop iterations per callback.
                #
                # Safety: base_dly is always >= 1 sample (0.5ms @ 48kHz = 24 samples).
                # Read positions are always behind write positions by at least base_dly
                # samples, so writes and reads within the same buffer never alias.
                idx_fc = self._cb_indices[:frame_count]  # pre-allocated float index array
                write_pos = ((self._chorus_write + idx_fc) % buf_len).astype(np.int32)
                self._chorus_buf_l[write_pos] = mixed_l
                self._chorus_buf_r[write_pos] = mixed_r

                wet_l = self._cb_wet_l[:frame_count]
                wet_r = self._cb_wet_r[:frame_count]
                wet_l.fill(0.0)
                wet_r.fill(0.0)
                sample_f = idx_fc + 1.0  # 1-based sample offsets for phase advance
                for vi in range(n_voices):
                    phases = (self._chorus_phases[vi] + phase_inc * sample_f) % (2.0 * np.pi)
                    mod_smp = (np.sin(phases) * self.chorus_depth * max_dly_s).astype(np.int32)
                    rp = (write_pos - np.maximum(1, base_dly + mod_smp)) % buf_len
                    wet_l += self._chorus_buf_l[rp]
                    wet_r += self._chorus_buf_r[rp]
                    self._chorus_phases[vi] = float(phases[-1])
                self._chorus_write = int((write_pos[-1] + 1) % buf_len)

                scale = 1.0 / n_voices
                mx = float(self.chorus_mix)
                cho_l = self._cb_cho_l[:frame_count]
                cho_r = self._cb_cho_r[:frame_count]
                np.multiply(mixed_l, 1.0 - mx, out=cho_l)
                cho_l += wet_l * (scale * mx)
                np.multiply(mixed_r, 1.0 - mx, out=cho_r)
                cho_r += wet_r * (scale * mx)
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
                if ds >= frame_count:
                    # Vectorized path: read positions are at least frame_count samples
                    # behind write positions, so no intra-buffer feedback aliasing.
                    # Replaces O(frame_count) Python iterations with numpy array ops.
                    # Minimum useful delay time = frame_count/sample_rate = ~5.3ms at
                    # 256 samples; any musically meaningful delay exceeds this easily.
                    idx_fc = self._cb_indices[:frame_count]
                    write_pos = ((self._delay_write + idx_fc) % buf_len).astype(np.int32)
                    read_pos  = (write_pos - ds) % buf_len
                    wet_l = self._delay_buf_l[read_pos]
                    wet_r = self._delay_buf_r[read_pos]
                    self._delay_buf_l[write_pos] = mixed_l + fb * wet_l
                    self._delay_buf_r[write_pos] = mixed_r + fb * wet_r
                    mixed_l[:] = mixed_l * (1.0 - dm) + wet_l * dm
                    mixed_r[:] = mixed_r * (1.0 - dm) + wet_r * dm
                    self._delay_write = int((write_pos[-1] + 1) % buf_len)
                else:
                    # Short delay (< frame_count samples): per-sample loop required
                    # to correctly propagate intra-buffer feedback. Rare in practice.
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
                    if self._pending_all_notes_off:
                        # Mode-switch path: silence all voices at the bottom of the
                        # fade, then stop. No fade-in — new mode starts from silence.
                        for v in self.voices:
                            v.reset()
                        self._arp_held_notes.clear(); self._arp_sequence.clear()
                        self._arp_note_playing = None; self._arp_sample_counter = 0
                        self._fx_tail_samples = 0
                        self._pending_all_notes_off = False
                    else:
                        self._mute_ramp_fadein = self._MUTE_RAMP_LEN  # arm fade-in

            if self._mute_ramp_fadein > 0:
                ramp_start = 1.0 - (self._mute_ramp_fadein / self._MUTE_RAMP_LEN)
                ramp_end   = 1.0 - max(0, self._mute_ramp_fadein - frame_count) / self._MUTE_RAMP_LEN
                ramp = np.linspace(ramp_start, ramp_end, frame_count, dtype=np.float32)
                mixed_l *= ramp
                mixed_r *= ramp
                self._mute_ramp_fadein = max(0, self._mute_ramp_fadein - frame_count)

            # Square waves have high RMS relative to peak so they get slightly less drive.
            # Sine is quieter by nature and gets a small boost. Saw/tri at unity.
            comp = 0.9 if self.waveform in ["sine", "pure_sine"] else (0.75 if self.waveform == "square" else 1.0)
            # drive controls soft-clip saturation character — amp_level only.
            # master_volume is applied AFTER saturation as a clean linear gain so both
            # controls have full, independent audible range without cancelling each other.
            drive = self.amp_level_current * comp
            # tanh soft-clip: warm, analog saturation. Normalized by tanh(drive) so output
            # reaches full scale at unity drive regardless of waveform compensation.
            # Normalization factor clamped to avoid division by near-zero at very low drive.
            norm = np.tanh(max(drive, 0.01))
            sat_l = mixed_l * drive * gain_ramp
            mixed_l = np.tanh(sat_l) / norm * self.master_volume
            sat_r = mixed_r * drive * gain_ramp
            mixed_r = np.tanh(sat_r) / norm * self.master_volume

            # Engine-level inter-buffer crossfade: blend from the last buffer's final
            # post-tanh output toward the new output over _TRANSITION_XF_SAMPLES samples.
            # This hides FIR frequency-change transients at MONO/UNISON note transitions.
            # Applied post-tanh so _last_output_L/R stores the actual output value —
            # guarantees exact sample-0 continuity regardless of drive or gain_ramp changes.
            if self._transition_xf_remaining > 0:
                n_xf = min(self._transition_xf_remaining, frame_count)
                p = np.linspace(0.0, float(n_xf) / self._TRANSITION_XF_SAMPLES,
                                n_xf, dtype=np.float32)
                mixed_l[:n_xf] = self._last_output_L * (1.0 - p) + mixed_l[:n_xf] * p
                mixed_r[:n_xf] = self._last_output_R * (1.0 - p) + mixed_r[:n_xf] * p
                self._transition_xf_remaining -= n_xf
            # Store post-tanh last sample so the next crossfade can start from the exact
            # output value — eliminates tanh/gain rounding mismatch at buffer boundaries.
            self._last_output_L = float(mixed_l[-1])
            self._last_output_R = float(mixed_r[-1])
            # Use pre-allocated int32 buffer — write L/R interleaved via assignment.
            # Assignment to an int32 slice does implicit float→int truncation regardless
            # of numpy version; np.clip(..., out=int32) requires casting='unsafe' in
            # numpy >= 1.24 and would silently fail (caught by the except block = silence).
            out = self._cb_out[:frame_count * 2]
            out[0::2] = np.clip(mixed_l * 8388607, -8388607, 8388607)
            out[1::2] = np.clip(mixed_r * 8388607, -8388607, 8388607)
            # paInt24: view int32 as uint8, take the 3 LSBs per word (little-endian).
            # Avoids the astype('<i4') copy — int32 view is already correct on LE systems.
            out24 = out.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
            return (out24, pyaudio.paContinue)
        except Exception as e:
            import traceback; traceback.print_exc()
            # Silence: 3 bytes per sample × 2 channels × frame_count frames
            return (bytes(frame_count * 2 * 3), pyaudio.paContinue)

    def note_on(self, note: int, velocity: int = 127):
        self.held_notes.add(note)
        # Maintain ordered stack for MONO/UNISON last-note priority.
        # Re-insert at end so the most recently pressed note is always last.
        if note in self._held_notes_ordered:
            self._held_notes_ordered.remove(note)
        self._held_notes_ordered.append(note)
        self._held_notes_vel[note] = velocity / 127.0
        self.midi_event_queue.put({'type': 'note_on', 'note': note, 'velocity': velocity / 127.0})

    def note_off(self, note: int, velocity: int = 0):
        self.held_notes.discard(note)
        if note in self._held_notes_ordered:
            self._held_notes_ordered.remove(note)
        self._held_notes_vel.pop(note, None)
        self.midi_event_queue.put({'type': 'note_off', 'note': note, 'velocity': velocity / 127.0})

    def all_notes_off(self):
        """Silence all voices. Called from the UI thread (mode switch, panic).

        Routes the reset through the event queue so it executes on the audio
        thread at the start of the next buffer — never mid-callback, which
        previously caused torn voice state and crackles during mode switches.
        """
        self.held_notes.clear()
        self._held_notes_ordered.clear()
        self._held_notes_vel.clear()
        self.midi_event_queue.put({'type': 'all_notes_off'})

    def soft_all_notes_off(self):
        """Click-free mode-switch silence: 8ms fade-out then reset all voices.

        Uses the existing mute ramp to ramp the output to zero before cutting,
        eliminating the amplitude discontinuity that causes audible clicks when
        switching modes while notes are sounding. No fade-in follows — the new
        mode starts from silence. Use all_notes_off() for panic/emergency cuts.
        """
        self.held_notes.clear()
        self._held_notes_ordered.clear()
        self._held_notes_vel.clear()
        self.midi_event_queue.put({'type': 'soft_all_notes_off'})

    def pitch_bend_change(self, value: int): self.pitch_bend_target = ((value - 8192) / 8192.0) * 2.0

    def modulation_change(self, value: int): self.mod_wheel = value / 127.0

    def get_current_params(self) -> dict:
        """Return a snapshot of the current synth parameter state from the UI thread.

        Reads the live engine attributes directly (safe for reading scalars from
        the UI thread between audio callbacks). Used by modes that need to save
        and restore state around a temporary parameter override (e.g. piano mode).
        """
        return {
            "waveform":       self.waveform,
            "octave":         self.octave,
            "noise_level":    self.noise_level_target,
            "amp_level":      self.amp_level,
            "cutoff":         self.cutoff,
            "hpf_cutoff":     self.hpf_cutoff,
            "resonance":      self.resonance,
            "hpf_resonance":  self.hpf_resonance,
            "key_tracking":   self.key_tracking_target,
            "attack":         self.attack,
            "decay":          self.decay,
            "sustain":        self.sustain,
            "release":        self.release,
            "rank2_enabled":  self.rank2_enabled,
            "rank2_waveform": self.rank2_waveform,
            "rank2_detune":   self.rank2_detune,
            "rank2_mix":      self.rank2_mix,
            "sine_mix":       self.sine_mix,
            "lfo_freq":       self.lfo_freq,
            "lfo_vco_mod":    self.lfo_vco_mod,
            "lfo_vcf_mod":    self.lfo_vcf_mod,
            "lfo_vca_mod":    self.lfo_vca_mod,
            "lfo_shape":      self.lfo_shape,
            "lfo_target":     self.lfo_target,
            "lfo_depth":      self.lfo_depth,
            "delay_time":     self.delay_time,
            "delay_feedback": self.delay_feedback,
            "delay_mix":      self.delay_mix,
            "chorus_rate":    self.chorus_rate,
            "chorus_depth":   self.chorus_depth,
            "chorus_mix":     self.chorus_mix,
            "chorus_voices":  self.chorus_voices,
            "arp_enabled":    self.arp_enabled,
            "arp_mode":       self.arp_mode,
            "arp_gate":       self.arp_gate,
            "arp_range":      self.arp_range,
            "voice_type":     self.voice_type,
            "feg_attack":     self.feg_attack,
            "feg_decay":      self.feg_decay,
            "feg_sustain":    self.feg_sustain,
            "feg_release":    self.feg_release,
            "feg_amount":     self.feg_amount,
            "filter_drive":   self.filter_drive_target,
            "filter_routing": self.filter_routing,
        }

    def update_parameters(self, **kwargs):
        """Update synth parameters from the UI thread.

        All writes are enqueued and applied on the audio thread at the start
        of the next buffer via _process_midi_events(). This eliminates the
        25+ shared-attribute race conditions between the Textual UI event loop
        and the PyAudio callback thread that caused clicks when knobs were
        moved while notes were playing.
        """
        self.midi_event_queue.put({'type': 'param_update', 'params': kwargs})

    def drum_trigger(self, note: int, velocity: int, params: dict):
        """Enqueue an atomic drum trigger: params + note_on bundled as one event.

        Unlike calling update_parameters() + note_on() separately, this ensures
        the drum's synthesis parameters are applied immediately before its note_on
        in the same audio-thread operation. This prevents parameter cross-
        contamination when multiple drums trigger on the same sequencer step
        (e.g. Kick + HiHat: without this, the last drum's params apply to ALL voices).
        """
        self.midi_event_queue.put({
            'type': 'drum_trigger',
            'note': note,
            'velocity': velocity,
            'params': params,
        })

    def close(self):
        self.running = False
        if self.stream: self.stream.stop_stream(); self.stream.close()
        if self.audio: self.audio.terminate()

    def is_available(self) -> bool: return AUDIO_AVAILABLE and self.running

    def warm_up(self):
        if self.is_available(): self.note_on(0, 1); self.note_off(0)
