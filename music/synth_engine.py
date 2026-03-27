"""Synthesizer engine for generating audio waveforms."""
import os
import sys
import math
import struct
import ctypes
import platform
import numpy as np
import threading
import queue
import random as _rnd
from typing import Optional, List

# Check for sounddevice availability
try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    sd = None


class Voice:
    """Individual synthesizer voice with its own oscillator and envelope."""

    def __init__(self, sample_rate: int, voice_index: int = 0, buffer_size: int = 512):
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
        # When > 0, caps the exponential release time constant to this value (seconds)
        # for the duration of this release.  Set on the outgoing voice during a MONO
        # voice steal so its fade-out finishes in ≤15ms regardless of the release knob.
        # Prevents two simultaneous pure-sine voices from beating together long enough
        # to become audible.  Cleared to 0.0 in reset() so normal note-offs are unaffected.
        self.release_time_cap: float = 0.0

        # Portamento glide state.
        # _glide_from_freq > 0 means a pitch glide is in progress.
        # v.frequency is updated each buffer by exponential interpolation from
        # _glide_from_freq toward base_frequency over _glide_elapsed samples.
        # Because v.frequency drives both the oscillator AND the key-tracking
        # filter cutoff, the VCF cutoff glides in sync with the pitch — no
        # sudden coefficient jump at high resonance.
        self._glide_from_freq: float = 0.0   # source frequency (0 = no glide)
        self._glide_elapsed:   int   = 0     # samples elapsed since glide start

        # Ghost voice flag: True when this voice has been promoted to the ghost pool
        # after being stolen while still audible.  Ghost voices drain their release tail
        # to silence at a capped rate but are never assigned new notes and are excluded
        # from gain normalisation.  Reset to False in reset().
        self.is_ghost: bool = False

        # Per-voice filter cutoff smoothing: tracks the effective fl_lpf / fl_hpf used
        # in the previous buffer.  Interpolating toward the new value each buffer prevents
        # sudden coefficient jumps (from FEG restart, key-tracking note changes, or large
        # EG amounts) from creating state/coefficient mismatches that high-resonance filters
        # amplify into audible spikes.  -1.0 = uninitialised (set on first use).
        self.smooth_fl_lpf: float = -1.0
        self.smooth_fl_hpf: float = -1.0
        self.smooth_resonance: float = -1.0  # per-voice resonance smoothing, -1.0 = uninitialised

        # ARM Lite fast filter: scipy sosfilt and lfilter state per voice per rank.
        # None = uninitialised (allocated on first use or after voice.reset()).
        # Separate LPF and HPF zi arrays per rank so rank1 and rank2 have independent state.
        self._arm_lpf_zi_r1: Optional[np.ndarray] = None
        self._arm_lpf_zi_r2: Optional[np.ndarray] = None
        self._arm_hpf_zi_r1: Optional[np.ndarray] = None
        self._arm_hpf_zi_r2: Optional[np.ndarray] = None
        self._arm_dcblock_zi: Optional[np.ndarray] = None

        # ── Pre-allocated hot-path working buffers ────────────────────────────
        # Each voice carries its own set of reusable numpy arrays so the audio
        # callback never calls np.zeros / np.ones / np.arange mid-flight.
        # Sized at 4× buffer_size to cover all oversampling settings (1×/2×/4×)
        # without reallocation.  Memory cost: ~36 KB per voice.
        _vbs = buffer_size * 4   # max oversampled length  (e.g. 480×4 = 1920)
        # Oscillator waveform output — one buffer per oscillator rank / sub-osc.
        self._v_osc_buf:     np.ndarray = np.zeros(_vbs, dtype=np.float32)
        self._v_osc_buf_r2:  np.ndarray = np.zeros(_vbs, dtype=np.float32)
        self._v_osc_buf_sin: np.ndarray = np.zeros(_vbs, dtype=np.float32)
        # Phase accumulation and normalised-phase intermediate for waveform math.
        self._v_phase_arr:   np.ndarray = np.zeros(_vbs, dtype=np.float32)
        self._v_tnorm_buf:   np.ndarray = np.zeros(_vbs, dtype=np.float32)
        # Envelope, per-sample time array, and onset ramp (base value = 1.0 = flat).
        self._v_env_buf:     np.ndarray = np.zeros(buffer_size, dtype=np.float32)
        self._v_times_buf:   np.ndarray = np.zeros(buffer_size, dtype=np.float32)
        self._v_onset_ramp:  np.ndarray = np.ones(buffer_size,  dtype=np.float32)
        # Filter output (shared across ladder and SVF — never used simultaneously).
        self._v_flt_buf:     np.ndarray = np.zeros(buffer_size, dtype=np.float32)
        # DC blocker output buffer (desktop non-scipy path).
        self._v_dc_buf:      np.ndarray = np.zeros(buffer_size, dtype=np.float32)
        # ── Analog capacitor simulation state ───────────────────────────────────
        # cap_env: slow RMS follower for varicap filter darkening (Feature 1).
        self.cap_env: float = 0.0
        # sustain_cap: capacitor charge for sustain leakage (Feature 2); reset on trigger.
        self.sustain_cap: float = 1.0
        # cap_ws_state: leaky integrator state for waveform rounding (Feature 3).
        self.cap_ws_state: float = 0.0
        # cap waveshaper working buffer — same size convention as other _v_* buffers.
        self._v_cap_ws_buf:  np.ndarray = np.zeros(_vbs, dtype=np.float32)

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
            # Reset capacitor simulation states on every new trigger.
            self.cap_env      = 0.0
            self.sustain_cap  = 1.0
            self.cap_ws_state = 0.0
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
        # Reset ARM Lite scipy filter states so the next note starts clean.
        self._arm_lpf_zi_r1 = None
        self._arm_lpf_zi_r2 = None
        self._arm_hpf_zi_r1 = None
        self._arm_hpf_zi_r2 = None
        self._arm_dcblock_zi = None
        self.release_time_cap = 0.0
        self.is_ghost = False
        self.cap_env      = 0.0
        self.sustain_cap  = 1.0
        self.cap_ws_state = 0.0
        self._glide_from_freq = 0.0
        self._glide_elapsed   = 0


def list_output_devices() -> list:
    """Return all output-capable audio devices as [(index, name), ...].

    Uses sounddevice (PortAudio) for enumeration. Safe to call from the UI
    process before the audio engine is started. Returns an empty list if
    sounddevice is unavailable.

    On Windows, PortAudio lists the same physical device once per host API
    (MME, DirectSound, WASAPI, WDM-KS). Duplicates are collapsed by name,
    preferring WASAPI for best latency.
    """
    if not AUDIO_AVAILABLE or sd is None:
        return []
    try:
        hostapis = sd.query_hostapis()
        devices  = sd.query_devices()

        candidates = {}  # name -> (index, hostapi_name)
        for i, d in enumerate(devices):
            if d['max_output_channels'] > 0:
                name         = d['name']
                hostapi_name = hostapis[d['hostapi']]['name']
                if name not in candidates:
                    candidates[name] = (i, hostapi_name)
                elif 'WASAPI' in hostapi_name:
                    # Prefer WASAPI over MME / DirectSound on Windows
                    candidates[name] = (i, hostapi_name)

        return [(idx, name) for name, (idx, _) in candidates.items()]
    except Exception:
        return []


def list_audio_backends() -> list:
    """Return all host APIs that have at least one output device, as [(name, hostapi_index), ...].

    Used by the config screen to populate the audio backend selector.
    Returns an empty list if sounddevice is unavailable.
    """
    if not AUDIO_AVAILABLE or sd is None:
        return []
    try:
        hostapis = sd.query_hostapis()
        devices  = sd.query_devices()

        # Count output-capable devices per host API
        output_counts = {}
        for d in devices:
            if d['max_output_channels'] > 0:
                hid = d['hostapi']
                output_counts[hid] = output_counts.get(hid, 0) + 1

        result = []
        for hid, api in enumerate(hostapis):
            if output_counts.get(hid, 0) > 0:
                result.append((api['name'], hid))
        return result
    except Exception:
        return []


def list_output_devices_for_backend(hostapi_name: str) -> list:
    """Return output devices for a specific host API as [(index, name), ...].

    Unlike list_output_devices(), this does NOT collapse duplicates — it shows
    every device that belongs to the requested backend so the user can pick
    the exact ASIO/WASAPI/DirectSound device they want.
    Returns an empty list if sounddevice is unavailable or backend not found.
    """
    if not AUDIO_AVAILABLE or sd is None:
        return []
    try:
        hostapis = sd.query_hostapis()
        devices  = sd.query_devices()

        # Find the hostapi index matching the name
        target_hid = next(
            (hid for hid, api in enumerate(hostapis) if api['name'] == hostapi_name),
            None
        )
        if target_hid is None:
            return []

        return [
            (i, d['name'])
            for i, d in enumerate(devices)
            if d['hostapi'] == target_hid and d['max_output_channels'] > 0
        ]
    except Exception:
        return []


def get_hostapi_index_for_backend(backend_name: str) -> Optional[int]:
    """Convert a backend name (e.g., 'ASIO', 'WASAPI') to its host_api index.

    Returns the numeric host_api index used by sounddevice, or None if not found.
    """
    if not AUDIO_AVAILABLE or sd is None or not backend_name:
        return None
    try:
        backends = list_audio_backends()
        for name, hid in backends:
            if name == backend_name:
                return hid
        return None
    except Exception:
        return None


def recommended_audio_backend() -> str:
    """Return the recommended audio backend name for the current OS and installed drivers.

    Priority order per platform:
      Windows : ASIO (lowest latency, direct hardware) → WASAPI → DirectSound → System Default
      macOS   : Core Audio (only real option) → System Default
      Linux   : JACK (pro real-time) → PipeWire → PulseAudio → ALSA → System Default

    Only returns a backend that is actually present in the PortAudio device list.
    Falls back to "System Default" if nothing preferred is found.
    """
    import platform
    available_names = [name for name, _ in list_audio_backends()]

    def first_match(preferences):
        for pref in preferences:
            for name in available_names:
                if pref.lower() in name.lower():
                    return name
        return "System Default"

    system = platform.system()
    if system == "Windows":
        return first_match(["ASIO", "WASAPI", "DirectSound"])
    elif system == "Darwin":
        return first_match(["Core Audio"])
    else:  # Linux and others
        return first_match(["JACK", "PipeWire", "PulseAudio", "ALSA"])


class SynthEngine:
    """8-voice polyphonic synthesizer engine with stabilized gain and master volume."""

    # ARM devices (armv7l/aarch64) use reduced settings to fit within the CPU budget
    # of a Raspberry Pi or similar single-board computer.
    _IS_ARM = platform.machine() in ("armv7l", "aarch64")

    def __init__(self, output_device_index=None, buffer_size=480, audio_backend=None,
                 enable_oversampling=True, level_shm_name=None):
        # Sample rate default: 48000 Hz. Override with ACORDES_SAMPLE_RATE env var
        # for quick testing without touching code, e.g.:
        #   ACORDES_SAMPLE_RATE=44100 uv run python main.py
        # Valid values: 44100, 48000, 88200, 96000. Anything else falls back to 48000.
        _VALID_RATES = {44100, 48000, 88200, 96000}
        _env_rate = int(os.environ.get("ACORDES_SAMPLE_RATE", "0"))
        self.sample_rate = _env_rate if _env_rate in _VALID_RATES else 48000
        # ARM: floor at 2048 (~46ms at 44100Hz). The Pi 4's single usable Python
        # core (GIL) must handle both Textual UI and the audio callback. 1024
        # (~43ms) leaves too little headroom and causes periodic underruns that
        # sound like a tremolo/LFO wobble on every note. 4096 gives the kernel
        # scheduler enough slack to let the callback always finish in time.
        # The user-configured value is respected if it is larger (e.g. 8192).
        # Desktop uses the config value directly (default 480 = 10ms).
        self.buffer_size = max(2048, buffer_size) if self._IS_ARM else buffer_size
        # ARM: 6 voices on armv7l (1GB Pi 4), 6 on aarch64 (64-bit Pi).
        # scipy C-level filters replaced the Python per-sample loops that were
        # the bottleneck (160ms callbacks). With the fast path the Pi 4 has
        # enough headroom to run 6 voices comfortably at 2048-sample buffers.
        import platform as _plat
        self.num_voices = 6 if _plat.machine() == "armv7l" else (6 if self._IS_ARM else 8)
        # Always use float32 for the sounddevice stream. PortAudio's ALSA backend
        # negotiates format with the driver internally and handles float32->S16_LE
        # conversion via ALSA's plug layer. Forcing int16 at the PortAudio level
        # on bcm2835 causes unreliable period negotiation and xruns on ARM.
        self._output_dtype = 'float32'
        # Startup diagnostic string populated after stream init (ARM only).
        # Read by engine_proxy._audio_process_main and forwarded to LoadingScreen.
        self._startup_info = ""
        # Import scipy signal functions once at init time so the audio callback
        # never pays the import cost. Falls back gracefully if scipy is not installed.
        #
        # _scipy_sosfilt: ARM only. Replaces the 4-pole Moog ladder + SVF with a
        #   2nd-order biquad approximation. Necessary on ARM because the Python
        #   per-sample ladder loop cannot run in real-time. On desktop the Moog
        #   ladder runs fine and must not be bypassed (would be a quality regression).
        #
        # _scipy_lfilter: All platforms. Used only for the DC blocker — an exact
        #   implementation (not an approximation), gives ~100x speedup with zero
        #   quality trade-off. Especially valuable when oversampling is enabled.
        self._scipy_sosfilt = None
        self._scipy_lfilter = None
        try:
            from scipy.signal import sosfilt as _sosfilt, lfilter as _lfilter
            if self._IS_ARM:
                self._scipy_sosfilt = _sosfilt
            self._scipy_lfilter = _lfilter
        except ImportError:
            pass
        self.stream = None
        # -1 = No Audio mode (engine runs silently, no audio stream opened)
        # -2 = System Default (None passed to sounddevice — OS chooses the output)
        # None = system default (same as -2, legacy behavior)
        # >=0 = specific sounddevice device index
        self._output_device_index = output_device_index
        self._audio_backend = audio_backend  # Host API name (e.g., "ASIO", "WASAPI")
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
        # TPDF dither: triangular probability density function noise applied
        # after final clip so any downstream float32→int16 conversion
        # (WASAPI shared mode, ALSA plug layer, 16-bit DAC) is dithered,
        # trading quantisation distortion for inaudible low-level noise.
        #
        # Architecture inspired by Chris Johnson's airwindows TPDFDither
        # (https://github.com/airwindows/airwindows, MIT licence).
        # Key insight adopted: separate per-channel RNG states guarantee that
        # L and R dither sequences never share a window of the generator,
        # eliminating any inter-channel correlation at the bit level.
        # The TPDF formula r1-r2 (two independent uniforms differenced) is
        # mathematically identical to the airwindows r1+r2-1 construction;
        # both produce a triangular distribution on (-1 LSB, +1 LSB).
        #
        # Our vectorised implementation generates one double-length buffer
        # per channel (2×frame_count) in a single RNG call, then splits it
        # into the two halves used for r1 and r2 — halving generator
        # invocations versus the naive 4-call approach while preserving
        # full independence between L and R channels.  Pre-allocated buffers
        # avoid heap allocation in the audio callback hot path.
        self._dither_buf_l  = np.zeros(2 * _bs, dtype=np.float32)  # L channel: [r1 | r2]
        self._dither_buf_r  = np.zeros(2 * _bs, dtype=np.float32)  # R channel: [r1 | r2]
        self._DITHER_AMP: float = 1.0 / 32768.0   # 1 LSB at 16-bit depth
        # Independent seeds for L and R; prefix 0xACC0 = ACCO(rdes)
        self._dither_rng_l  = np.random.default_rng(0xACC05000)
        self._dither_rng_r  = np.random.default_rng(0xACC05001)
        # Float index array reused for vectorized ring-buffer index math
        self._cb_indices  = np.arange(_bs, dtype=np.float32)
        # Oversample-length index array: covers up to 4× oversampling so
        # _generate_waveform can compute phase arrays in-place without np.arange.
        self._cb_indices_4x = np.arange(_bs * 4, dtype=np.float32)

        # Tier 2: pre-allocated ring-buffer write-index arrays.
        # Chorus and delay previously called .astype(np.int32) every buffer,
        # creating 480-element int32 arrays that were immediately discarded.
        # These int32 views accept float→int assignment directly (numpy truncates).
        self._cb_idx_f       = np.zeros(_bs, dtype=np.float32)  # float temp for index math
        self._cb_cho_wr_idx  = np.zeros(_bs, dtype=np.int32)    # chorus write positions
        self._cb_dly_wr_idx  = np.zeros(_bs, dtype=np.int32)    # delay write positions

        # Tier 3: shared ramp buffers replacing np.linspace allocations.
        # _cb_ramp_buf   — primary scalar ramp (filter-switch, mute, onset, XF).
        # _cb_ramp_cos   — intermediate for the pre-gate S-curve cosine computation.
        self._cb_ramp_buf    = np.zeros(_bs, dtype=np.float32)
        self._cb_ramp_cos    = np.zeros(_bs, dtype=np.float32)

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

        # ── VU Meter audio level caching (for visualizer) ─────────────────────
        # Real-time max amplitude per channel from last buffer. Computed in
        # _audio_callback and cached for UI thread polling (thread-safe float read).
        self.level_l = 0.0
        self.level_r = 0.0
        # Optional shared memory block supplied by SynthEngineProxy so the main
        # process can read VU meter levels across the subprocess boundary.
        self._level_shm = None
        if level_shm_name:
            try:
                from multiprocessing.shared_memory import SharedMemory
                self._level_shm = SharedMemory(name=level_shm_name)
            except Exception:
                pass

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
        # Engine-level resonance snaps instantly: per-voice smooth_resonance (coeff 0.65,
        # ~64ms) already handles UNISON artifact prevention on the ladder filter.
        # A slow coefficient here made the parameter feel dead — changes took 300-400ms
        # to audibly register because two smoothing stages were stacked in series.
        self.resonance_smoothing = 0.0  # instant; artifact guard lives in per-voice smooth
        self.hpf_resonance_current   = 0.0
        self.hpf_resonance_target    = 0.0
        # HPF resonance has no per-voice smooth (used directly in SVF call).
        # Fast 3-buffer ramp (~32ms at 48kHz/512) softens SVF integrator shock on
        # rapid changes without making the parameter feel sluggish.
        self.hpf_resonance_smoothing = 0.50
        self.noise_level_current = 0.0
        self.noise_level_target  = 0.0
        self.noise_level_smoothing = 0.90
        self.key_tracking         = 0.5   # hasattr sentinel — required for param_update dispatch
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
        # Portamento glide time in seconds.  0.0 = off (hard frequency change).
        # When > 0, MONO and UNISON legato triggers glide the oscillator frequency
        # (and therefore the key-tracking filter cutoff) from the previous note's
        # pitch to the new one over this duration.  Exponential interpolation in
        # frequency space gives equal-tempered semitone steps the same duration
        # regardless of interval size (1 semitone glides as smoothly as 1 octave).
        # Subtle default (20ms) hides the abrupt frequency step without sounding
        # like a pronounced slide effect.  Shorter than 40ms so the glide finishes
        # before the next note arrives at fast tempos (300+ BPM sixteenth notes ~50ms).
        self.portamento_time: float = 0.020   # seconds; 0 = hard, 0.020 = subtle legato
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
        self._transition_xf_remaining: int = 0   # samples left in active crossfade
        self._TRANSITION_XF_SAMPLES:  int = 48  # 48 smp ≈ 1.1ms: inaudible, covers UNISON freq-step artifact

        # FX tail drain counter — keeps the audio callback alive (not early-returning
        # silence) while Delay / Chorus ring buffers still have audible wet content.
        # Set to the maximum possible tail length (delay_max_seconds * feedback_decay)
        # whenever a note is triggered; decremented by frame_count each buffer when
        # active_count == 0.  0 means "no tail to drain — safe to output silence."
        # Max tail = 2s delay × ~10 echoes at 0.9 feedback ≈ 20s, but we cap at 10s
        # (480000 samples) to avoid infinite draining if feedback is maxed.
        self._fx_tail_samples = 0        # samples remaining to drain after all voices silent
        self._FX_TAIL_MAX     = int(self.sample_rate * 10.0)   # 10s ceiling

        # Pre-generated metronome click buffers (float32, stereo interleaved).
        # Generated once at init; played back by mixing into the output when
        # a 'metronome_tick' event is received. Avoids any secondary audio stream
        # opening (which conflicts with ASIO exclusive-mode drivers).
        self._metro_normal_buf, self._metro_accent_buf = self._generate_metro_clicks()
        self._metro_click_buf: Optional[np.ndarray] = None  # currently playing click
        self._metro_click_pos: int = 0                      # read position in click buf

        # Startup silence counter — outputs zero samples for first ~1s after stream starts.
        # Eliminates click artifacts from filter/DC blocker transients during warm-up.
        # 1 second allows all DSP state (filters, DC blockers, LFO, arpeggiator) to fully settle.
        self._startup_silence_samples = int(self.sample_rate * 1.0)  # 1 second of silence

        # ── Output transformer simulation ──────────────────────────────────────
        # Models the subtle tonal shaping of an analog output transformer:
        # a gentle one-pole LP at 18 kHz softens extreme highs (roundness), and
        # a small even-harmonic injection adds warmth proportional to signal level.
        # State is per-engine (post-mix, stereo). Shares the scipy lfilter fast
        # path with the per-voice DC blocker for zero extra Python overhead.
        _xfmr_c = math.exp(-2.0 * math.pi * 18000.0 / self.sample_rate)
        self._XFMR_LP_B    = np.array([(1.0 - _xfmr_c)], dtype=np.float64)
        self._XFMR_LP_A    = np.array([1.0, -_xfmr_c],   dtype=np.float64)
        self._XFMR_LP_ZI_L = np.zeros(1, dtype=np.float64)  # filter memory L
        self._XFMR_LP_ZI_R = np.zeros(1, dtype=np.float64)  # filter memory R
        self._XFMR_EVEN    = 0.04   # 2nd harmonic coefficient (subtle asymmetry)
        self._xfmr_sq_buf  = np.zeros(self.buffer_size, dtype=np.float32)  # pre-alloc

        # ── Tube compressor ─────────────────────────────────────────────────────
        # Warm RMS compression at the output stage. Per-buffer RMS detection
        # avoids per-sample overhead. Soft-knee 3:1 at -10 dBFS with program-
        # dependent attack/release ballistics. 2nd harmonic injection scales
        # with gain reduction, adding warmth only when the compressor is working.
        self._comp_env       = 0.0    # RMS envelope follower state
        self._comp_gain      = 1.0    # current smoothed gain (1.0 = unity)
        self._COMP_THRESH    = 0.316  # -10 dBFS threshold
        self._COMP_RATIO_EXP = 0.6667 # 1 - 1/ratio (3:1 → 0.667)
        self._COMP_ENV_ATK   = 0.60   # fast attack (~1 buffer response)
        self._COMP_ENV_REL   = 0.08   # slower release (~8 buffers / ~85 ms)
        self._COMP_GAIN_ATK  = 0.40   # gain ramp down quickly
        self._COMP_GAIN_REL  = 0.04   # gain recovers slowly (tube pumping character)
        self._COMP_MAKEUP    = 1.15   # +1.2 dB makeup gain
        self._COMP_HARMONIC  = 0.12   # 2nd harmonic depth during compression

        # ── Analog capacitor simulation constants ──────────────────────────────
        # Varicap: attack rate for the per-voice RMS envelope follower (~200ms).
        self._CAP_VARICAP_ATK   = 0.003
        # Varicap: maximum fractional cutoff reduction at full signal level (10%).
        self._CAP_VARICAP_DEPTH = 0.10
        # Sustain leakage: one-sample charge loss, giving a ~6.5 s time constant.
        self._CAP_SUSTAIN_LEAK  = 1.0 / (6.5 * self.sample_rate)
        # Capacitor waveshaper: dry/wet blend (7% wet — transparent).
        self._CAP_WS_BLEND      = 0.07
        # Capacitor waveshaper: RC time constant normalised to oscillator period.
        self._CAP_WS_RC         = 1.0
        # RC gate curve: tau as fraction of ramp duration (1-exp(-1/0.33)=0.953).
        self._CAP_GATE_TAU      = 0.33

        self.pitch_bend = 0.0
        self.pitch_bend_target = 0.0
        self.pitch_bend_smoothing = 0.85
        self.mod_wheel = 0.0

        # ── Oversampling configuration ─────────────────────────────────────────
        # 2× internal oscillator oversampling for alias-free sawtooth/square/triangle.
        # Always disabled on ARM (CPU budget). On desktop controlled by the
        # enable_oversampling constructor parameter (from config_manager).
        self.ENABLE_OVERSAMPLING = enable_oversampling and not self._IS_ARM
        self.OVERSAMPLE_FACTOR = 2 if self.ENABLE_OVERSAMPLING else 1
        self.OVERSAMPLE_SAMPLE_RATE = self.sample_rate * self.OVERSAMPLE_FACTOR
        self._downsample_filter_taps = None     # Pre-computed FIR filter (initialized below)

        # ── ARM effect bypass flags ────────────────────────────────────────────
        # Chorus and delay are expensive BBD-style ring-buffer DSP blocks. On ARM
        # they are force-bypassed regardless of the UI knob value to keep the Pi 4
        # callback well under its CPU budget. Desktop builds leave them enabled.
        self.ENABLE_CHORUS = not self._IS_ARM
        self.ENABLE_DELAY  = not self._IS_ARM

        # ── ARM diagnostic counters ────────────────────────────────────────────
        # Accumulate xrun and slow-callback events instead of printing from the
        # audio thread. print() grabs the GIL and can itself trigger more xruns.
        # get_arm_diagnostics() exposes these for the UI to read safely.
        if self._IS_ARM:
            import time as _arm_time_mod
            self._perf_counter     = _arm_time_mod.perf_counter
            self._arm_xrun_count   = 0   # driver xrun events
            self._arm_slow_cb_count = 0  # callbacks that used >50% of deadline
            self._arm_cb_count     = 0   # total callbacks processed

        self.voices: List[Voice] = [Voice(self.sample_rate, i, _bs) for i in range(self.num_voices)]

        # Ghost voice pool: pre-allocated extra voices that hold release tails from
        # stolen POLY voices.  When a real voice is stolen while still audible, its
        # full state is copied here so the tail plays out undisturbed while the real
        # voice slot takes the new note.  Ghost voices are excluded from gain
        # normalisation and are never assigned new notes.
        # ARM (Pi): 1 ghost slot (CPU budget is tight).  Desktop: 2 ghost slots.
        _ghost_count = 1 if self._IS_ARM else 2
        self._ghost_voices: List[Voice] = [
            Voice(self.sample_rate, self.num_voices + i, _bs)
            for i in range(_ghost_count)
        ]
        # Maximum release time (seconds) allowed for a ghost voice.
        # Keeps tails short enough to free the slot quickly for the next steal.
        self._GHOST_RELEASE_CAP: float = 0.08   # 80ms

        self.held_notes: set = set()
        self.midi_event_queue = queue.Queue()

        # Initialize polyphase downsampling filter for oversampling
        self._create_polyphase_filter()

        if self._output_device_index == -1:
            # No Audio mode: engine processes MIDI but produces no sound.
            # No audio stream is opened; _audio_callback is never called.
            self.running = True

        elif AUDIO_AVAILABLE and sd is not None:
            try:
                # Resolve the device index to use:
                # - specific index (>=0): use as-is (already encodes the host API)
                # - None or -2 (system default): if a backend is specified, find its
                #   default output device so ASIO/WASAPI/etc. is honoured correctly.
                #   Without this, sounddevice picks the OS default (WASAPI on Windows)
                #   even when the user explicitly chose a different backend.
                device_index = None
                if self._output_device_index is not None and self._output_device_index >= 0:
                    device_index = self._output_device_index
                elif self._audio_backend:
                    hid = get_hostapi_index_for_backend(self._audio_backend)
                    if hid is not None:
                        try:
                            api_info = sd.query_hostapis(hid)
                            default_dev = api_info.get('default_output_device', -1)
                            if default_dev >= 0:
                                device_index = default_dev
                        except Exception:
                            pass  # Fall through to OS default if lookup fails
                elif self._IS_ARM:
                    # On ARM with no explicit device configured, scan for the
                    # bcm2835 headphone device by name instead of using the ALSA
                    # "default". The ALSA default can be PulseAudio or HDMI,
                    # both of which add resampling and latency.  Going directly
                    # to the hardware device avoids that entire routing layer.
                    device_index = self._find_arm_headphone_device()
                    if device_index is not None:
                        print(f"[audio] ARM: selected device index {device_index} "
                              f"({sd.query_devices(device_index)['name']})", flush=True)
                    else:
                        print("[audio] ARM: bcm2835 headphone device not found, using ALSA default", flush=True)

                # ARM: use an explicit numeric latency that matches the buffer
                # size so PortAudio doesn't add a second layer of buffering on
                # top of our blocksize.  'high' is vague and driver-dependent.
                _latency = (self.buffer_size / self.sample_rate) if self._IS_ARM else 'low'
                self.stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    blocksize=self.buffer_size,
                    device=device_index,
                    channels=2,
                    dtype=self._output_dtype,
                    callback=self._audio_callback,
                    latency=_latency,
                )
                self.stream.start()
                self.running = True
                self._elevate_audio_priority()

                actual_blocksize = self.stream.blocksize
                if self._IS_ARM:
                    # Collect startup diagnostics into _startup_info so the
                    # LoadingScreen can display them cleanly instead of having
                    # raw print() calls bleed through the Textual UI.
                    dev_name = "default"
                    if device_index is not None:
                        try:
                            dev_name = sd.query_devices(device_index)['name']
                            # Truncate long device names so they fit the UI box.
                            if len(dev_name) > 28:
                                dev_name = dev_name[:25] + "..."
                        except Exception:
                            pass
                    buf_ms  = actual_blocksize / self.sample_rate * 1000
                    lat_ms  = self.stream.latency * 1000
                    self._startup_info = (
                        f"Device  : {dev_name}\n"
                        f"Rate    : {self.sample_rate} Hz\n"
                        f"Buffer  : {actual_blocksize} smp  ({buf_ms:.1f} ms)\n"
                        f"Voices  : {self.num_voices}\n"
                        f"Latency : {lat_ms:.1f} ms"
                    )
                else:
                    self._startup_info = ""
                    if actual_blocksize != self.buffer_size:
                        print(f"Buffer size mismatch: requested {self.buffer_size}, got {actual_blocksize} samples")
                        print(f"  Latency: {actual_blocksize / self.sample_rate * 1000:.2f}ms")
            except Exception as e:
                print(f"Audio initialization failed: {e}")
                self.running = False

    def _design_biquad_lpf_sos(self, cutoff: float, resonance: float) -> np.ndarray:
        """Design a 4-pole (24dB/oct) lowpass filter as two cascaded biquad sections.

        Returns a (2, 6) SOS array for use with scipy.signal.sosfilt.
        Two sections in cascade = 4-pole rolloff matching the desktop Moog ladder slope.

        Q is spread asymmetrically between stages to approximate the Moog ladder's
        resonance character: stage 1 carries most of the resonance peak (forward
        emphasis), stage 2 is kept near Butterworth (stable, adds rolloff only).
        At resonance=0.0 both stages are Butterworth (Q=0.707) — flat passband.
        At resonance=1.0 stage 1 reaches Q=12 (near self-oscillation), stage 2 stays
        at Q=1.2 (prevents runaway instability that a symmetric Q cascade would have).
        """
        sr = self.sample_rate
        f0 = float(np.clip(cutoff, 20.0, sr * 0.45))
        # Stage 1: carries the resonance peak (Q scales aggressively with resonance).
        Q1 = max(0.5, 0.707 + resonance * 11.293)   # 0.707 → 12.0
        # Stage 2: near-Butterworth, just adds rolloff slope.
        Q2 = max(0.5, 0.707 + resonance * 0.493)    # 0.707 → 1.2

        def _biquad_lpf_coeffs(f, Q):
            w0 = 2.0 * math.pi * f / sr
            cos_w0 = math.cos(w0)
            sin_w0 = math.sin(w0)
            alpha = sin_w0 / (2.0 * Q)
            b0 = (1.0 - cos_w0) * 0.5
            b1 = 1.0 - cos_w0
            b2 = (1.0 - cos_w0) * 0.5
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha
            return [b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0]

        s1 = _biquad_lpf_coeffs(f0, Q1)
        s2 = _biquad_lpf_coeffs(f0, Q2)
        return np.array([s1, s2])

    def _design_biquad_hpf_sos(self, cutoff: float, resonance: float) -> np.ndarray:
        """Design a resonant 2nd-order highpass biquad (RBJ Audio EQ Cookbook).

        Returns a (1, 6) SOS array for use with scipy.signal.sosfilt.
        Replaces the Chamberlin SVF HPF Python loop on ARM for real-time use.
        resonance 0.0 -> Q=0.707 (Butterworth), 1.0 -> Q=10.0 (near self-oscillation).
        """
        sr = self.sample_rate
        f0 = float(np.clip(cutoff, 20.0, sr * 0.45))
        Q = max(0.5, 0.707 + resonance * 9.293)
        w0 = 2.0 * math.pi * f0 / sr
        cos_w0 = math.cos(w0)
        sin_w0 = math.sin(w0)
        alpha = sin_w0 / (2.0 * Q)
        b0 = (1.0 + cos_w0) * 0.5
        b1 = -(1.0 + cos_w0)
        b2 = (1.0 + cos_w0) * 0.5
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha
        return np.array([[b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0]])

    def _find_arm_headphone_device(self) -> Optional[int]:
        """Scan the sounddevice device list for the bcm2835 headphone output.

        Returns the device index of the first output device whose name contains
        'Headphones' or 'bcm2835' (case-insensitive), or None if not found.
        Used on ARM so we bypass the ALSA default which may route through
        PulseAudio, adding resampling and latency artefacts.
        """
        try:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev['max_output_channels'] < 1:
                    continue
                name = dev.get('name', '').lower()
                if 'headphones' in name or ('bcm2835' in name and 'hdmi' not in name):
                    return i
        except Exception:
            pass
        return None

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

    def _generate_metro_clicks(self):
        """Generate simple metronome clicks using white noise with decay.

        Returns (normal_buf, accent_buf) as float32 numpy arrays.
        Both clicks use white noise for a natural "tick" sound.
        """
        duration_s = 0.007  # 25 ms per click
        n = int(self.sample_rate * duration_s)

        # White noise with exponential decay
        noise = np.random.randn(n).astype(np.float32)
        t = np.linspace(0, duration_s, n, endpoint=False, dtype=np.float32)
        decay = np.exp(-t / 0.009).astype(np.float32)

        # Normal click: quieter (for off-beats)
        normal_buf = (noise * decay * 0.3).astype(np.float32)

        # Accent click: louder (for beat emphasis)
        accent_buf = (noise * decay * 0.5).astype(np.float32)

        return normal_buf, accent_buf

    def _create_polyphase_filter(self):
        """ABOUTME: Create 31-tap Hamming-windowed sinc FIR lowpass filter for 4× downsampling.
        ABOUTME: Cutoff at 20 kHz with > 60dB attenuation above Nyquist."""
        N = 31  # Tap count (odd for symmetry)
        n = np.arange(N) - N // 2  # Center at 0: [-15, -14, ..., 0, ..., 14, 15]

        # Normalized cutoff frequency: 20 kHz relative to the oversampled Nyquist.
        # OVERSAMPLE_FACTOR sets the internal rate (e.g., 2× → 96 kHz at 48 kHz output).
        # Using the actual oversample rate avoids cutting audio above ~10 kHz when
        # OVERSAMPLE_FACTOR=2 (a hardcoded 192 kHz denominator would be wrong there).
        oversampled_nyquist = self.sample_rate * self.OVERSAMPLE_FACTOR / 2.0
        normalized_cutoff = 20000.0 / oversampled_nyquist

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

        # Three leaky integrators with different decay rates approximate 1/f (pink)
        # spectrum (Voss-McCartney method).  Each channel is a 1st-order IIR:
        #   y[n] = a * y[n-1] + b * x[n]
        # which maps directly to scipy.lfilter(b=[b], a=[1, -a], x, zi=zi).
        # This eliminates the Python per-sample loop entirely.
        #
        # Initial-state vector: zi[0] = a * y_prev so that y[0] is continuous
        # with the previous buffer's last output sample.
        if self._scipy_lfilter is not None:
            _lf = self._scipy_lfilter
            _params = [
                (0.99765, 0.0990460,  self._pink_state[0]),
                (0.96494, 0.2965164,  self._pink_state[1]),
                (0.57115, 1.0526500,  self._pink_state[2]),
            ]
            channels = []
            new_states = list(self._pink_state)
            for ch, (a_c, b_c, s_prev) in enumerate(_params):
                y, _ = _lf([b_c], [1.0, -a_c],
                            white.astype(np.float64),
                            zi=np.array([a_c * s_prev]))
                channels.append(y)
                new_states[ch] = float(y[-1])
            self._pink_state = np.array(new_states, dtype=np.float32)
            pink = ((channels[0] + channels[1] + channels[2]) * 0.333333).astype(np.float32)
        else:
            # Fallback scalar loop when scipy is unavailable
            pink = np.zeros(num_samples, dtype=np.float32)
            state = self._pink_state.copy()
            for i in range(num_samples):
                state[0] = 0.99765 * state[0] + white[i] * 0.0990460
                state[1] = 0.96494 * state[1] + white[i] * 0.2965164
                state[2] = 0.57115 * state[2] + white[i] * 1.0526500
                pink[i] = (state[0] + state[1] + state[2]) * 0.333333
            self._pink_state = state

        return pink.astype(np.float32)

    def _fill_linspace(self, buf: np.ndarray, start: float, stop: float, n: int) -> np.ndarray:
        """Write a linear ramp from start to stop into buf[:n] with zero allocation.

        Equivalent to np.linspace(start, stop, n, dtype=np.float32) but uses the
        pre-allocated self._cb_indices array and in-place multiply/add so no heap
        allocation occurs.  Returns a view of buf[:n].
        """
        view = buf[:n]
        if n == 1:
            view[0] = start
            return view
        scale = np.float32((stop - start) / (n - 1))
        np.multiply(self._cb_indices[:n], scale, out=view)
        view += np.float32(start)
        return view

    def _generate_waveform(self, waveform: str, frequency: float, num_samples: int, start_phase: float, oversample_factor: int = 1, _out: Optional[np.ndarray] = None, _phases: Optional[np.ndarray] = None) -> tuple[np.ndarray, float]:
        # Handle noise waveforms first (they don't use frequency/phase)
        if waveform == "noise_white":
            samples = np.random.randn(num_samples).astype(np.float32) * 0.5
            return samples, start_phase
        elif waveform == "noise_pink":
            samples = self._generate_pink_noise(num_samples) * 0.5
            return samples, start_phase

        # Regular pitched waveforms use phase accumulation.
        # Support 4× oversampling: generate at 192 kHz if oversample_factor=4.
        effective_sample_rate = self.sample_rate * oversample_factor
        effective_num_samples = num_samples * oversample_factor

        phase_inc = np.float32(2.0 * np.pi * frequency / effective_sample_rate)

        # Phase accumulation — use pre-allocated buffer when supplied to avoid
        # np.arange + broadcast allocation (~7 KB per call at 4× oversampling).
        if _phases is not None and len(_phases) >= effective_num_samples:
            phases = _phases[:effective_num_samples]
            # Compute phases[i] = start_phase + i * phase_inc in-place using the
            # pre-built oversample-length index array (self._cb_indices_4x).
            np.multiply(self._cb_indices_4x[:effective_num_samples], phase_inc, out=phases)
            phases += np.float32(start_phase)
        else:
            phases = start_phase + np.arange(effective_num_samples) * phase_inc

        # Normalised phase t_norm = (phase / 2π) % 1  — used by triangle/saw/square.
        # Uses pre-allocated _v_tnorm_buf when _phases buffer is the voice's own array.
        t_norm = (phases / np.float32(2.0 * np.pi)) % np.float32(1.0)

        # Output buffer: use caller-supplied pre-allocated array when provided.
        if _out is not None and len(_out) >= effective_num_samples:
            samples = _out[:effective_num_samples]
            if waveform == "pure_sine":
                np.sin(phases, out=samples)
            elif waveform == "sine":
                np.sin(phases, out=samples)
                samples *= np.float32(0.99)
                # Compute 2nd harmonic into t_norm (reuse as temp since it's been read)
                np.multiply(phases, np.float32(2.0), out=t_norm)
                np.sin(t_norm, out=t_norm)
                samples += t_norm * np.float32(0.01)
                # Restore t_norm for PolyBLEP (not needed for sine — PolyBLEP skips sine)
            elif waveform == "triangle":
                np.subtract(t_norm, np.float32(0.5), out=samples)
                np.abs(samples, out=samples)
                samples *= np.float32(4.0)
                samples -= np.float32(1.0)
            elif waveform == "square":
                np.sin(phases, out=samples)
                np.sign(samples, out=samples)
            else:
                # Sawtooth (default)
                np.multiply(t_norm, np.float32(2.0), out=samples)
                samples -= np.float32(1.0)
        else:
            if waveform == "pure_sine":
                samples = np.sin(phases)
            elif waveform == "sine":
                # Vintage-warm sine: fundamental + 1% 2nd harmonic for subtle colour.
                samples = np.sin(phases) * 0.99 + np.sin(2.0 * phases) * 0.01
            elif waveform == "triangle":
                samples = 4.0 * np.abs(t_norm - 0.5) - 1.0
            elif waveform == "square":
                samples = np.where(np.sin(phases) >= 0, 1.0, -1.0)
            else:
                # Sawtooth (default)
                samples = 2.0 * t_norm - 1.0

        # Apply PolyBLEP anti-aliasing to band-limited waveforms.
        # Skipped on ARM: single-core Pi 4 cannot afford it without xruns.
        if not self._IS_ARM and waveform in ["sawtooth", "square", "triangle"]:
            samples = self._apply_polyblep(waveform, samples, phases, frequency, effective_num_samples, effective_sample_rate)

        final_phase = float((start_phase + effective_num_samples * phase_inc) % (2.0 * np.pi))
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

    def _apply_envelope(self, voice: Voice, samples: np.ndarray, num_samples: int,
                        _env_buf: Optional[np.ndarray] = None,
                        _times_buf: Optional[np.ndarray] = None) -> np.ndarray:
        dt = np.float32(1.0 / self.sample_rate)
        VEL_C, VEL_F = 1.3, 0.15
        v_scaled = VEL_F + (1.0 - VEL_F) * (voice.velocity ** VEL_C)
        v_int = 1.0 * v_scaled

        # Time array: voice.envelope_time + [0, dt, 2dt, …, (n-1)*dt].
        # Use pre-allocated buffer when supplied; otherwise allocate (fallback).
        if _times_buf is not None and len(_times_buf) >= num_samples:
            times = _times_buf[:num_samples]
            # Inline linspace to avoid _fill_linspace function-call overhead (called 8x per buffer).
            t_start = np.float32(voice.envelope_time)
            if num_samples > 1:
                np.multiply(self._cb_indices[:num_samples], dt, out=times)
                times += t_start
            else:
                times[0] = t_start
        else:
            times = voice.envelope_time + np.arange(num_samples) * dt

        # Envelope output — use pre-allocated buffer when supplied.
        if _env_buf is not None and len(_env_buf) >= num_samples:
            envelope = _env_buf[:num_samples]
            envelope.fill(0.0)
        else:
            envelope = np.zeros(num_samples, dtype=np.float32)
        if voice.is_releasing:
            # rel_mod scales release time by note-off velocity (soft release -> longer tail).
            # time_const is the RC time constant of the exponential decay — the /4 divisor
            # that was here previously made releases sound 4x shorter than the UI indicated.
            rel_mod = 1.0 / (0.5 + voice.release_velocity)
            time_const = max(0.005, self.release * rel_mod)
            # On a MONO voice steal the outgoing voice gets a short cap so two pure-sine
            # voices don't beat together long enough to produce an audible AM artifact.
            if voice.release_time_cap > 0.0:
                time_const = min(time_const, voice.release_time_cap)
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
            # Feature 2: Sustain capacitor leakage — dielectric loss on the hold
            # capacitor. Very long sustained notes drift slightly downward over
            # ~6.5 seconds, flooring at 65% of the sustain level. Models the slow
            # charge bleed that occurs in real analog envelope generator hold stages.
            if not voice.is_releasing:
                sustain_mask = times >= dec_end
                if sustain_mask.any():
                    voice.sustain_cap = max(0.65, voice.sustain_cap - self._CAP_SUSTAIN_LEAK * num_samples)
                    envelope[sustain_mask] *= voice.sustain_cap
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

        Vectorized using scipy.lfilter when available: each pole is a 1st-order
        IIR y[n] = alpha*x_in[n] + (1-alpha)*y[n-1] with resonance feedback on
        the input.  The feedback is linearised per-buffer (using prev_state from
        the last buffer boundary) which is equivalent to the one-sample-delayed
        feedback the original loop used, extended to one-buffer delay — inaudible
        at normal buffer sizes (256-512 samples).
        """
        alpha   = float(np.clip(2 * np.pi * cutoff / self.sample_rate, 0.0, 1.0))
        a1      = 1.0 - alpha
        res_fb  = res * 0.95

        if self._scipy_lfilter is not None:
            # Exact vectorization: absorb the resonance feedback into the IIR
            # coefficient so no per-buffer approximation is needed.
            #
            # Per-sample recurrence:
            #   y[n] = alpha*(x[n] - res_fb*y[n-1]) + a1*y[n-1]
            #        = alpha*x[n] + (a1 - alpha*res_fb)*y[n-1]
            #        = alpha*x[n] + alpha_r*y[n-1]
            # where alpha_r = 1 - alpha*(1 + res_fb).
            # This is an exact 1st-order IIR; lfilter computes it sample-accurately
            # with no approximation and no feedback delay.
            # Initial state: zi[0] = alpha_r * y[-1] = alpha_r * prev_state.
            _lf     = self._scipy_lfilter
            x64     = samples.astype(np.float64)
            alpha_r = 1.0 - alpha * (1.0 + res_fb)   # pole 1 effective coefficient
            y1, _   = _lf([alpha], [1.0, -alpha_r], x64,
                          zi=np.array([alpha_r * float(prev_state)]))
            state   = float(y1[-1])
            filtered = (y1 if filter_type == "lpf" else x64 - y1).astype(np.float32)

            # Pole 2: same exact transformation, independent state
            state_b = float(prev_state_b)
            if filter_type == "lpf" and res > 0.1:
                alpha_r2 = 1.0 - alpha * (1.0 + res_fb * 0.5)
                y2, _    = _lf([alpha], [1.0, -alpha_r2],
                               filtered.astype(np.float64),
                               zi=np.array([alpha_r2 * state_b]))
                state_b  = float(y2[-1])
                filtered = y2.astype(np.float32)

            return filtered, state, state_b

        # Fallback scalar loop when scipy is unavailable
        filtered = np.zeros_like(samples, dtype=np.float32)
        state = float(prev_state)
        for i in range(len(samples)):
            inp   = samples[i] - res_fb * state
            state = alpha * inp + a1 * state
            filtered[i] = state if filter_type == "lpf" else samples[i] - state

        state_b = float(prev_state_b)
        if filter_type == "lpf" and res > 0.1:
            for i in range(len(filtered)):
                inp2    = filtered[i] - res_fb * 0.5 * state_b
                state_b = alpha * inp2 + a1 * state_b
                filtered[i] = state_b

        return filtered, state, state_b

    def _filter_ladder_process(self, samples: np.ndarray, cutoff: float,
                               prev_states: list, res: float = 0.0,
                               _out: Optional[np.ndarray] = None) -> tuple:
        """4-pole Moog ladder filter — warm, strong resonance, self-oscillates near res=0.99.

        Uses one-sample-delayed feedback (inaudible at 48 kHz) so the per-sample
        computation is independent and the loop is simple to follow.
        Alpha is capped at 0.95 to prevent IIR instability at high cutoff frequencies
        (alpha > 1.0 violates the stability condition of the discrete integrator).
        """
        sr = self.sample_rate
        fc = float(np.clip(cutoff, 20.0, sr * 0.45))
        # Chamberlin/bilinear-adjacent coefficient: 2·sin(π·fc/sr) tracks the analog
        # prototype more accurately than the forward-Euler 2π·fc/sr, especially above
        # fc/sr ≈ 0.1 where the Euler form over-rotates and undershoots the true cutoff.
        alpha = float(np.clip(2.0 * math.sin(math.pi * fc / sr), 0.0, 0.95))
        # k normalisation: resonance feedback scales down with alpha so the
        # filter remains unconditionally stable; k→1.0 approaches self-oscillation.
        # Scale by 1.2 for more aggressive resonance character
        k = float(np.clip(res * 1.2 * (1.0 / (1.0 + alpha)), 0.0, 0.99))

        a1 = 1.0 - alpha

        # Scalar loop: the 4-stage Moog ladder has nonlinear tanh feedback between
        # stages that makes it unsuitable for scipy.lfilter vectorization.
        # The global feedback (tanh(x - 4k*s3)) and stage-3 self-feedback
        # (s3 = tanh(a1*s3 + alpha*s2)) both use the previous SAMPLE's s3,
        # creating a tight per-sample dependency that cannot be safely extended
        # to per-buffer or per-chunk delays without audible artifacts at high resonance.
        N   = len(samples)
        # Use pre-allocated output buffer when supplied; otherwise allocate.
        if _out is not None and len(_out) >= N:
            out = _out[:N]
        else:
            out = np.zeros(N, dtype=np.float32)
        s0, s1, s2, s3 = prev_states[0], prev_states[1], prev_states[2], prev_states[3]

        for i in range(N):
            x0 = math.tanh(float(samples[i]) - 4.0 * k * s3)
            s0 = a1 * s0 + alpha * x0
            s1 = a1 * s1 + alpha * s0
            s2 = a1 * s2 + alpha * s1
            s3 = math.tanh(a1 * s3 + alpha * s2)
            out[i] = s3

        out *= 1.3
        return out, [s0, s1, s2, s3]

    def _filter_svf_process(self, samples: np.ndarray, cutoff: float,
                            lp_state: float, bp_state: float,
                            res: float = 0.0,
                            _out: Optional[np.ndarray] = None) -> tuple:
        """Chamberlin State Variable Filter — 2-pole LP output.

        Uses the correct Chamberlin update order (lp updated from previous bp, not
        the newly-computed bp) which is unconditionally stable for f <= 2*sqrt(q/2).
        Cutoff is hard-limited to sr/6 (~8kHz at 48kHz) to stay in the stable region.
        q=2 (no resonance) → q→0 (near self-oscillation); clamped to prevent blow-up.
        """
        sr = self.sample_rate
        fc = float(np.clip(cutoff, 20.0, sr * 0.45))
        f_raw = float(np.clip(2.0 * np.sin(np.pi * fc / sr), 0.0, 0.95))
        # More aggressive Q curve: higher resonance = higher Q (more pronounced peak)
        q = float(np.clip(0.5 + res * 10.0, 0.5, 10.5))
        # Chamberlin stability condition: f < sqrt(2/q).  Clamp f to 95% of the limit
        # to keep the filter stable at all resonance values without hard cutoff ceiling.
        f_max = math.sqrt(2.0 / q) * 0.95
        f = float(np.clip(f_raw, 0.0, f_max))

        N = len(samples)
        out = (_out[:N] if _out is not None and len(_out) >= N
               else np.zeros(N, dtype=np.float32))
        lp = lp_state
        bp = bp_state

        for i in range(N):
            # Correct Chamberlin order: lp uses previous bp, bp uses current hp
            lp = lp + f * bp              # integrate bp → lp (previous bp)
            hp = float(samples[i]) - lp - q * bp
            bp = bp + f * hp              # integrate hp → bp
            # Hard clamp prevents integrator blow-up at extreme q values.
            if lp > 4.0: lp = 4.0
            elif lp < -4.0: lp = -4.0
            if bp > 4.0: bp = 4.0
            elif bp < -4.0: bp = -4.0
            out[i] = lp

        return out, lp, bp

    def _filter_svf_hp_process(self, samples: np.ndarray, cutoff: float,
                               lp_state: float, bp_state: float,
                               res: float = 0.0, routing: str = "lp_hp",
                               _out: Optional[np.ndarray] = None) -> tuple:
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
        fc = float(np.clip(cutoff, 20.0, sr * 0.45))
        f_raw = float(np.clip(2.0 * np.sin(np.pi * fc / sr), 0.0, 0.95))
        # Full Q range for HPF: 0.5 (flat) → 10.0 (harsh resonant peak).
        # Previously capped at 4.0 which made the HP peak feel weak compared to the LP.
        # Matching the LP filter's Q range (0.5-10.5) gives the MS-20 HP+LP routing
        # its characteristic harshness when both peaks are pushed high simultaneously.
        q = float(np.clip(0.5 + res * 9.5, 0.5, 10.0))
        # Chamberlin stability condition: f < sqrt(2/q).  95% margin keeps filter stable
        # at high resonance + high cutoff combinations without a hard frequency ceiling.
        f_max = math.sqrt(2.0 / q) * 0.95
        f = float(np.clip(f_raw, 0.0, f_max))

        N = len(samples)
        out = (_out[:N] if _out is not None and len(_out) >= N
               else np.zeros(N, dtype=np.float32))
        lp = lp_state
        bp = bp_state

        # Routing is resolved once here so the inner loop contains no string
        # comparisons — each branch is a tight loop over samples only.
        if routing == "lp_hp":
            for i in range(N):
                lp = lp + f * bp
                hp = float(samples[i]) - lp - q * bp
                bp = bp + f * hp
                # Hard clamp prevents integrator blow-up at extreme q values.
                if lp > 4.0: lp = 4.0
                elif lp < -4.0: lp = -4.0
                if bp > 4.0: bp = 4.0
                elif bp < -4.0: bp = -4.0
                out[i] = hp
        elif routing == "bp_lp":
            for i in range(N):
                lp = lp + f * bp
                hp = float(samples[i]) - lp - q * bp
                bp = bp + f * hp
                if lp > 4.0: lp = 4.0
                elif lp < -4.0: lp = -4.0
                if bp > 4.0: bp = 4.0
                elif bp < -4.0: bp = -4.0
                out[i] = bp
        elif routing == "notch_lp":
            for i in range(N):
                lp = lp + f * bp
                hp = float(samples[i]) - lp - q * bp
                bp = bp + f * hp
                if lp > 4.0: lp = 4.0
                elif lp < -4.0: lp = -4.0
                if bp > 4.0: bp = 4.0
                elif bp < -4.0: bp = -4.0
                out[i] = float(samples[i]) - lp  # notch = input - lp (Chamberlin formula)
        else:  # "lp_lp"
            for i in range(N):
                lp = lp + f * bp
                hp = float(samples[i]) - lp - q * bp
                bp = bp + f * hp
                if lp > 4.0: lp = 4.0
                elif lp < -4.0: lp = -4.0
                if bp > 4.0: bp = 4.0
                elif bp < -4.0: bp = -4.0
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
        # Key tracking: shift cutoff proportionally with the actual sounding pitch.
        # Reference is C4 at the current octave setting — track_mult = 1.0 there.
        # base_frequency holds the raw MIDI frequency; apply the same octave shift
        # that the oscillator applies so the filter tracks the note you hear, not
        # the unshifted MIDI pitch (which caused ktrack to have no audible effect
        # when octave != 0, and weak effect when octave == 0 because the reference
        # was fixed at 261.63 regardless of the octave knob position).
        _oct_mult  = (2.0 ** self.octave) if (self.octave_enabled and self.octave != 0) else 1.0
        f_sounding = (voice.base_frequency or 261.63) * _oct_mult
        # C4 reference also shifts with the octave so track_mult stays 1.0 on C4.
        _ref_freq  = 261.63 * _oct_mult
        track_mult = 1.0 + self.key_tracking_current * (f_sounding / _ref_freq - 1.0)

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
            voice.smooth_resonance = self.resonance_current
        else:
            voice.smooth_fl_lpf = voice.smooth_fl_lpf * _SMOOTH_K + fl_lpf * (1.0 - _SMOOTH_K)
            voice.smooth_fl_hpf = voice.smooth_fl_hpf * _SMOOTH_K + fl_hpf * (1.0 - _SMOOTH_K)
            voice.smooth_resonance = voice.smooth_resonance * _SMOOTH_K + self.resonance_current * (1.0 - _SMOOTH_K)
        fl_lpf = voice.smooth_fl_lpf
        fl_hpf = voice.smooth_fl_hpf

        # Feature 1: Varicap — voltage-dependent filter modulation.
        # Loud signals increase the effective capacitance, darkening the filter
        # by up to 10%. Models the non-linear behaviour of varicap diodes used
        # in real analog filter circuits under high drive conditions.
        if fl_lpf > 0.0:
            sig_level = float(np.sqrt(np.mean(samples * samples)))
            voice.cap_env += (sig_level - voice.cap_env) * self._CAP_VARICAP_ATK
            fl_lpf = fl_lpf * (1.0 - self._CAP_VARICAP_DEPTH * voice.cap_env)
            fl_lpf = float(np.clip(fl_lpf, 20.0, 20000.0))

        # ── scipy fast path: biquad IIR (C code, GIL-free, ~100x faster) ───────
        # Replaces the per-sample Python loops for both HPF and LPF stages.
        # Uses RBJ cookbook 2nd-order IIR with sosfilt state continuity across buffers.
        if self._scipy_sosfilt is not None:
            _sosfilt = self._scipy_sosfilt
            # HPF stage (only if cutoff is meaningfully above DC — > 30 Hz)
            if fl_hpf > 30.0:
                hpf_sos = self._design_biquad_hpf_sos(fl_hpf, self.hpf_resonance_current)
                if rank == 1:
                    if voice._arm_hpf_zi_r1 is None:
                        voice._arm_hpf_zi_r1 = np.zeros((1, 2))
                    samples, voice._arm_hpf_zi_r1 = _sosfilt(hpf_sos, samples, zi=voice._arm_hpf_zi_r1)
                    samples = samples.astype(np.float32)
                else:
                    if voice._arm_hpf_zi_r2 is None:
                        voice._arm_hpf_zi_r2 = np.zeros((1, 2))
                    samples, voice._arm_hpf_zi_r2 = _sosfilt(hpf_sos, samples, zi=voice._arm_hpf_zi_r2)
                    samples = samples.astype(np.float32)
            # LPF stage: 2-section SOS (4-pole, 24dB/oct cascade)
            lpf_sos = self._design_biquad_lpf_sos(fl_lpf, voice.smooth_resonance)
            n_sections = lpf_sos.shape[0]   # 2 sections
            if rank == 1:
                if voice._arm_lpf_zi_r1 is None or voice._arm_lpf_zi_r1.shape[0] != n_sections:
                    voice._arm_lpf_zi_r1 = np.zeros((n_sections, 2))
                filtered, voice._arm_lpf_zi_r1 = _sosfilt(lpf_sos, samples, zi=voice._arm_lpf_zi_r1)
            else:
                if voice._arm_lpf_zi_r2 is None or voice._arm_lpf_zi_r2.shape[0] != n_sections:
                    voice._arm_lpf_zi_r2 = np.zeros((n_sections, 2))
                filtered, voice._arm_lpf_zi_r2 = _sosfilt(lpf_sos, samples, zi=voice._arm_lpf_zi_r2)
            return filtered.astype(np.float32)

        # ── HPF stage: resonant Chamberlin SVF (HP output) ───────────────────
        # Reuses the per-voice svf state slots (previously for LPF-SVF mode).
        hpf_lp_s = voice.filter_state_svf1_lp if rank == 1 else voice.filter_state_svf2_lp
        hpf_bp_s = voice.filter_state_svf1_bp if rank == 1 else voice.filter_state_svf2_bp
        samples, hpf_lp_s, hpf_bp_s = self._filter_svf_hp_process(
            samples, fl_hpf, hpf_lp_s, hpf_bp_s, self.hpf_resonance_current,
            routing=self.filter_routing, _out=voice._v_flt_buf)
        if rank == 1:
            voice.filter_state_svf1_lp, voice.filter_state_svf1_bp = hpf_lp_s, hpf_bp_s
        else:
            voice.filter_state_svf2_lp, voice.filter_state_svf2_bp = hpf_lp_s, hpf_bp_s

        # ── LPF stage: 4-pole Moog ladder (always) ───────────────────────────

        # Thermal noise floor — ~-100 dBFS (amplitude 1e-5), inaudible in isolation
        # but prevents filter dead-zone lock when self-oscillating at max resonance,
        # and adds a subtle analog "air" that's felt rather than heard in the mix.
        samples = samples + np.random.randn(len(samples)).astype(np.float32) * 1e-5

        ladder_s = voice.filter_state_ladder1 if rank == 1 else voice.filter_state_ladder2
        filtered, ladder_s = self._filter_ladder_process(
            samples, fl_lpf, ladder_s, voice.smooth_resonance, _out=voice._v_flt_buf)
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

        # scipy fast path: lfilter (C code, GIL-free).
        # DC blocker H(z) = (1 - z^-1)/(1 - coeff*z^-1); b=[1,-1], a=[1,-coeff].
        # Transposed DF-II initial state: zi[0] = -x_prev + coeff * y_prev.
        if self._scipy_lfilter is not None:
            b_dc = np.array([1.0, -1.0])
            a_dc = np.array([1.0, -coeff])
            if voice._arm_dcblock_zi is None:
                voice._arm_dcblock_zi = np.array([-voice.dc_blocker_x + coeff * voice.dc_blocker_y])
            filtered, zf = self._scipy_lfilter(b_dc, a_dc, samples.astype(np.float64),
                                               zi=voice._arm_dcblock_zi)
            voice._arm_dcblock_zi = zf
            voice.dc_blocker_x = float(samples[-1])
            voice.dc_blocker_y = float(filtered[-1])
            return filtered.astype(np.float32)

        xp, yp = voice.dc_blocker_x, voice.dc_blocker_y
        n = len(samples)
        # All Voice instances have _v_dc_buf pre-allocated in __init__ — no hasattr needed.
        filtered = voice._v_dc_buf[:n]
        for i in range(n):
            filtered[i] = samples[i] - xp + coeff * yp
            xp, yp = samples[i], filtered[i]
        voice.dc_blocker_x, voice.dc_blocker_y = xp, yp
        return filtered

    def _sanitize_signal(self, samples: np.ndarray) -> np.ndarray:
        """Replace NaN/Inf with zeros and hard-clip to ±2.0 in-place.

        Guards against NaN propagation from gain compensation at extreme alpha values.
        Called at the filter output stage — the only pipeline point where gain
        multiplication could theoretically produce Inf despite the formula clamping.
        ±2.0 ceiling is above tanh's linear region (tanh(2)≈0.964) so normal peaks
        are unaffected; only pathological values are clipped.
        In-place operations avoid allocation overhead on each per-voice call.
        """
        # Replace non-finite values (NaN/Inf/-Inf) with 0 in-place.
        np.nan_to_num(samples, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        np.clip(samples, -2.0, 2.0, out=samples)
        return samples

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
                for g in self._ghost_voices:
                    g.reset()
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
            elif e['type'] == 'metronome_tick':
                # Restart the pre-generated click playback from the beginning.
                # Choosing accent vs. normal click is decided by the sender.
                self._metro_click_buf = self._metro_accent_buf if e.get('accent') else self._metro_normal_buf
                self._metro_click_pos = 0
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
        # MONO and UNISON use gate behavior: velocity is ignored, amplitude is always full.
        # The envelope acts as a pure on/off gate rather than a velocity-sensitive amplifier.
        if self.voice_type in ("mono", "unison"):
            vel = 1.0
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
                # Capture oscillator phase and filter coefficient smoothers from the
                # outgoing voice.  Phase inheritance prevents destructive interference
                # during the dissolve overlap (two pure-sine voices at different phases
                # cancel and create a click at the steal moment).  Smooth variable
                # inheritance prevents a sudden jump in filter coefficients when key
                # tracking or the FEG leaves the cutoff at a different value than the
                # new voice's starting point.
                #
                # Ladder and SVF delay-line states are intentionally NOT inherited.
                # Each transfer introduces frequency-mismatch error: the filter
                # "remembers" energy at the old pitch, and when the new oscillator
                # drives it at a different pitch that stored energy rings at the wrong
                # frequency.  With high resonance (Q≈9) this is clearly audible on
                # pure-sine waveforms.  The DC blocker state IS inherited (see below)
                # because its settling error is small (~6% amplitude, decays in 4.5ms)
                # whereas not inheriting it causes a hard first-sample click.
                _old_phase      = old_v.phase
                _old_pre_gate   = old_v.pre_gate_progress
                _old_smooth_lpf = old_v.smooth_fl_lpf
                _old_smooth_hpf = old_v.smooth_fl_hpf
                _old_smooth_res = old_v.smooth_resonance
                # DC blocker state: inherit so the first output sample of the new
                # voice has no discontinuity.  The blocker computes y[n] = x[n] -
                # x[n-1] + R*y[n-1]; resetting x[n-1] and y[n-1] to zero causes
                # a step equal to the oscillator's current amplitude at sample 0,
                # producing an audible click with pure-sine waveforms.  Inheriting
                # the old voice's last x/y values eliminates that first-sample jump.
                # Any frequency-mismatch error decays in ~4.5ms (200 samples at R=0.995).
                _old_dc_x       = old_v.dc_blocker_x
                _old_dc_y       = old_v.dc_blocker_y
                # Onset ramp position: the onset ramp was designed to hide DC blocker
                # cold-start transients when triggering from silence.  During a live
                # steal the audio is already playing, the DC blocker state is inherited,
                # and there is no cold start — so the onset ramp must NOT reset to 0.
                # Resetting creates a hard dip to near-zero amplitude at every steal,
                # audible as a stutter on rapid playing regardless of attack time.
                _old_onset      = old_v.onset_samples

                # Dissolve: send outgoing voice into ADSR release (it fades naturally),
                # trigger incoming voice fresh (it attacks naturally).
                # Cap stolen voice release to 15ms so two simultaneous pure-sine voices
                # at different pitches do not beat long enough to produce audible AM.
                old_v.release(self.attack, self.decay, self.sustain, 1.0)
                old_v.release_time_cap = 0.015
                old_v.feg_release_level = self._feg_level_snapshot(old_v)
                old_v.feg_is_releasing = True
                old_v.feg_release_start = old_v.feg_time
                new_v.trigger(note, freq, vel)
                new_v.onset_ms = onset_ms_for_note
                # Phase continuity: match outgoing oscillator to prevent destructive
                # interference during the dissolve overlap period.
                new_v.phase = _old_phase
                # Gate bypass on steal: set gate fully open regardless of the outgoing
                # voice's gate position.  The pre-gate S-curve was designed to hide
                # the DC blocker cold-start transient on a fresh note from silence.
                # During a steal the DC blocker state IS inherited (see above), so
                # that transient is already handled — re-applying the gate ramp only
                # compounds the envelope attack with a second fade-in, producing a
                # 20-30ms near-silence window whenever the old voice was still in its
                # gate ramp (e.g. rapid staccato playing, half-pressed key bounces).
                # With gate=1.0, ADSR is the sole amplitude shaper and the CROSS
                # crossfade provides the click-free onset.  _old_pre_gate is kept for
                # reference in the portamento block above but not applied to the gate.
                new_v.pre_gate_progress = 1.0
                # Inherit coefficient smoothers so the filter cutoff does not jump.
                new_v.smooth_fl_lpf = _old_smooth_lpf
                new_v.smooth_fl_hpf = _old_smooth_hpf
                new_v.smooth_resonance = _old_smooth_res
                # Inherit DC blocker state and onset position (see capture comments above).
                new_v.dc_blocker_x  = _old_dc_x
                new_v.dc_blocker_y  = _old_dc_y
                new_v.onset_samples = _old_onset
                # Portamento glide: if enabled, slide from the old pitch to the new one.
                # Because v.frequency also drives key-tracking cutoff, the filter cutoff
                # glides in sync — no sudden coefficient jump at the steal moment.
                # Use base_frequency (target pitch) not frequency (mid-glide position) as
                # the glide source to prevent portamento accumulation at fast tempos: if we
                # used mid-glide position, each rapid steal would inherit the drifted frequency
                # and the pitch would never converge to any actual note.
                _glide_src = (old_v.base_frequency if old_v._glide_from_freq > 0.0
                              else old_v.frequency)
                if self.portamento_time > 0.0 and _glide_src and _glide_src != freq:
                    new_v._glide_from_freq = _glide_src
                    new_v._glide_elapsed   = 0
                else:
                    new_v._glide_from_freq = 0.0
                self._mono_primary = new_idx
                self.mono_voice_index = new_idx
                # Engine crossfade to hide any residual FIR boundary transient.
                self._transition_xf_remaining = self._TRANSITION_XF_SAMPLES
            else:
                # From silence: hard trigger on the primary slot, no glide.
                old_v._glide_from_freq = 0.0
                old_v.trigger(note, freq, vel)
                old_v.onset_ms = onset_ms_for_note
                old_v.phase = 0.0
                old_v.pre_gate_progress = 0.0

        elif self.voice_type == "unison":
            # Unison mode: all voices play same note with detuning spread.
            # Voices are detuned across ±unison_detune cents for the characteristic thick sound.
            n = len(self.voices)
            # _legato_base_phase is set by the first voice that takes the soft-trigger
            # (legato) path.  Initialise to voice 0's current phase so that voices
            # taking the soft path always have a valid anchor even if voice 0 itself
            # fell below the amplitude threshold and took the hard-trigger path instead.
            # (Without this initialisation, if voice 0 goes hard and voice 1 goes soft,
            # reading _legato_base_phase before it is ever assigned raises UnboundLocalError.)
            _legato_base_phase = self.voices[0].phase
            _legato_phase_set  = False   # True once an actual soft-trigger voice has anchored it
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
                    # True legato: envelope continues from its current position.
                    # feg_time and envelope_time are NOT reset — resetting them causes
                    # sudden filter coefficient jumps (high resonance → spike) and a
                    # double-attack dip.  pre_gate_progress is NOT reset — same reason
                    # as MONO steal (would stutter to zero on rapid re-triggers).
                    #
                    # Phase: voices are re-distributed evenly relative to the first
                    # soft-triggered voice's current phase.  After playing a note,
                    # the N detuned voices have drifted to random relative phases.
                    # Starting the next note with those arbitrary offsets produces
                    # unpredictable constructive or destructive interference — amplitude
                    # can land anywhere from near-zero to sqrt(N) depending on timing.
                    # Re-anchoring to even spacing gives a deterministic, balanced
                    # interference state on every legato trigger while still preserving
                    # the beating motion that develops naturally as voices drift apart.
                    if not _legato_phase_set:
                        _legato_base_phase = v.phase
                        _legato_phase_set  = True
                    v.phase = _legato_base_phase + i / n
                    # Gate bypass on legato retrigger: same reasoning as MONO steal.
                    # The envelope does NOT reset here (legato), so the gate ramp would
                    # sit at whatever low progress it had (e.g. 0.1 from a recent steal)
                    # and multiply down an already-playing envelope — audible as a quiet,
                    # smeared transition.  Gate fully open means the CROSS crossfade is
                    # the only smoothing needed; ADSR handles all amplitude shaping.
                    v.pre_gate_progress = 1.0
                    # Arm portamento glide from current pitch to new target.
                    # Each voice carries its own detuned source and target frequency
                    # so the detune spread glides in proportion across the interval.
                    # Use base_frequency as glide source (not mid-glide frequency) to
                    # prevent accumulating pitch drift at fast tempos — same reasoning
                    # as the MONO steal above.
                    _u_glide_src = (v.base_frequency if v._glide_from_freq > 0.0
                                    else v.frequency)
                    if self.portamento_time > 0.0 and _u_glide_src and _u_glide_src != detuned_freq:
                        v._glide_from_freq = _u_glide_src
                        v._glide_elapsed   = 0
                    else:
                        v._glide_from_freq = 0.0
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
                else:
                    # Hard trigger from true silence: full reset, no glide.
                    v._glide_from_freq = 0.0
                    v.trigger(note, detuned_freq, vel)
                    # Distribute phases evenly across one cycle instead of all-zero.
                    # All-zero phases create a brief phase-coherent comb filter on attack
                    # (voices start aligned, then drift apart) — audible as a metallic
                    # hollow artifact in the first 10-20ms of every hard note onset.
                    # Evenly distributing phases 0/N, 1/N, ... (N-1)/N means voices
                    # enter with full decorrelation: the comb filter never forms.
                    v.phase = i / n
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
            # Voice stealing — three-tier strategy:
            #
            # Tier 1 (safe steal): releasing voice with envelope < 5%.
            #   Nearly silent — steal directly.  No ghost needed; artifact is inaudible.
            #
            # Tier 2 (ghost promotion): steal is unavoidable but tail is still audible.
            #   Copy the stolen voice's full state into an available ghost slot so its
            #   tail drains undisturbed.  Trigger the new note in the freed real slot
            #   with a clean filter state.  Ghost release is capped at _GHOST_RELEASE_CAP
            #   so the slot comes free quickly.
            #
            # Tier 3 (brutal steal): no ghost slot free.
            #   Same as the original behaviour — accept the glitch risk.  Only happens
            #   under extreme polyphony abuse (all 8 real + all ghost slots occupied).

            # Priority metric: higher = more stealable.
            #   3 = releasing, not held, nearly silent (< 5%)   ← safe Tier 1
            #   2 = releasing, not held, still audible
            #   1 = releasing, still held
            #   0 = active
            def _steal_priority(v):
                if v.is_releasing and v.midi_note not in self.held_notes:
                    return (3, v.envelope_time) if v.last_envelope_level < 0.05 else (2, v.envelope_time)
                if v.is_releasing:
                    return (1, v.envelope_time)
                return (0, v.age)

            best_v = max(self.voices, key=_steal_priority)

            # Tier 1: tail is inaudible — steal directly (original fast path).
            steal_is_safe = (best_v.is_releasing
                             and best_v.midi_note not in self.held_notes
                             and best_v.last_envelope_level < 0.05)

            if not steal_is_safe:
                # Tier 2: try to promote the stolen voice to a ghost slot so its
                # tail completes without interruption.
                ghost_slot = next((g for g in self._ghost_voices if g.is_available()), None)
                if ghost_slot is not None:
                    # Copy all continuous state from the real voice to the ghost slot.
                    # This preserves oscillator phase, filter memory, and envelope level
                    # so the tail sounds identical to what would have played naturally.
                    ghost_slot.midi_note          = best_v.midi_note
                    ghost_slot.base_frequency     = best_v.base_frequency
                    ghost_slot.frequency          = best_v.frequency
                    ghost_slot.phase              = best_v.phase
                    ghost_slot.phase2             = best_v.phase2
                    ghost_slot.sine_phase         = best_v.sine_phase
                    ghost_slot.note_active        = best_v.note_active
                    ghost_slot.is_releasing       = best_v.is_releasing
                    ghost_slot.envelope_time      = best_v.envelope_time
                    ghost_slot.release_start_level = best_v.release_start_level
                    ghost_slot.last_envelope_level = best_v.last_envelope_level
                    ghost_slot.velocity           = best_v.velocity
                    ghost_slot.velocity_current   = best_v.velocity_current
                    ghost_slot.velocity_target    = best_v.velocity_target
                    ghost_slot.release_velocity   = best_v.release_velocity
                    ghost_slot.dc_blocker_x       = best_v.dc_blocker_x
                    ghost_slot.dc_blocker_y       = best_v.dc_blocker_y
                    ghost_slot.filter_state_ladder1 = list(best_v.filter_state_ladder1)
                    ghost_slot.filter_state_ladder2 = list(best_v.filter_state_ladder2)
                    ghost_slot.filter_state_svf1_lp = best_v.filter_state_svf1_lp
                    ghost_slot.filter_state_svf1_bp = best_v.filter_state_svf1_bp
                    ghost_slot.filter_state_svf2_lp = best_v.filter_state_svf2_lp
                    ghost_slot.filter_state_svf2_bp = best_v.filter_state_svf2_bp
                    ghost_slot.onset_samples      = best_v.onset_samples
                    ghost_slot.feg_time           = best_v.feg_time
                    ghost_slot.feg_is_releasing   = best_v.feg_is_releasing
                    ghost_slot.feg_release_start  = best_v.feg_release_start
                    ghost_slot.feg_release_level  = best_v.feg_release_level
                    ghost_slot._oversample_history[:]      = best_v._oversample_history
                    ghost_slot._oversample_history_r2[:]   = best_v._oversample_history_r2
                    ghost_slot._oversample_history_sine[:] = best_v._oversample_history_sine
                    # If the voice was still active (not yet releasing), put the ghost
                    # into release so it fades out naturally.
                    if ghost_slot.note_active and not ghost_slot.is_releasing:
                        ghost_slot.release(self.attack, self.decay, self.sustain, 1.0)
                    # Cap ghost release to _GHOST_RELEASE_CAP so the slot frees quickly.
                    ghost_slot.release_time_cap = self._GHOST_RELEASE_CAP
                    ghost_slot.is_ghost = True
                # Tier 3: no ghost available — fall through to brutal steal below.

            # Trigger the new note in the real voice slot with a clean filter state.
            # Filter and DC blocker states are cleared to prevent frequency-domain
            # glitches from stale integrator memory at the new note's frequency.
            best_v.filter_state_ladder1 = [0.0, 0.0, 0.0, 0.0]
            best_v.filter_state_ladder2 = [0.0, 0.0, 0.0, 0.0]
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

    def _audio_callback(self, outdata, frame_count, time, status):
        try:
            # Count driver-level underruns/overruns without printing. print()
            # from the audio thread grabs the GIL and can itself cause more xruns.
            if status and self._IS_ARM:
                self._arm_xrun_count += 1

            # ARM timing probe: sample every 500 callbacks (~23 s at 2048/44100).
            # Probing every call adds measurable overhead; sparse sampling is enough
            # to track whether the engine is staying within budget.
            _arm_probe = False
            if self._IS_ARM:
                self._arm_cb_count += 1
                if self._arm_cb_count % 500 == 0:
                    _arm_probe = True
                    _cb_t0 = self._perf_counter()

            # Output initial silence for ~50ms after startup to avoid filter transients
            if self._startup_silence_samples > 0:
                outdata.fill(0)
                self._startup_silence_samples -= frame_count
                return

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
            # Drive is a character knob — no smoothing needed.  Instant update
            # means the user hears the effect the moment they change the value.
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

            # Reclaim ghost slots that have finished their release tail.
            # A ghost voice that becomes available (envelope fully decayed) is reset
            # to a clean state so its slot is ready for the next promotion.
            for g in self._ghost_voices:
                if g.is_ghost and g.is_available():
                    g.reset()

            # Pre-count active voices BEFORE mixing so master_gain_target is
            # updated from the correct count and gain_ramp covers the full
            # transition in this buffer rather than lagging one buffer behind.
            # Ghost voices are intentionally excluded: they drain release tails but
            # must not inflate the gain denominator (they already output at 0.7×).
            active_count = sum(1 for v in self.voices if v.note_active or v.is_releasing)

            # Arm crossfade when voices just went silent this buffer.
            # Without this, the last non-zero sample of a release sits in
            # _last_output_L/R but _transition_xf_remaining is 0, so the
            # next buffer's first sample jumps from that level to 0 — a hard
            # click at the tail end of every note.  Setting the crossfade here
            # blends the last output toward zero over the first 48 samples of
            # the now-silent buffer, making the tail inaudible.
            if active_count == 0 and self._last_output_L != 0.0:
                self._transition_xf_remaining = self._TRANSITION_XF_SAMPLES

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
                if self._fx_tail_samples <= 0 and self._metro_click_buf is None:
                    outdata.fill(0)
                    return
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
            #
            # For POLY, count only actively-playing (non-releasing) voices.
            # Including releasing voices in the count causes a gain snap-down on every
            # note onset in melodic play: the release tail of the previous note briefly
            # overlaps the new note onset (active_count=2), instantly dropping gain to
            # 1/sqrt(2), then the tail finishes and gain slowly recovers over ~220ms —
            # producing a visible and audible volume bump on each note.
            # Releasing voices are already decaying naturally via their envelope; they
            # don't need additional gain compensation.
            playing_count = sum(1 for v in self.voices if v.note_active)
            gain_count = 1 if self.voice_type in ("mono", "unison") else max(playing_count, 1)
            self.master_gain_target = 1.0 / np.sqrt(gain_count) if gain_count > 1 else 1.0
            # Snapshot gain AFTER the target is known but BEFORE smoothing,
            # so gain_ramp interpolates from the previous buffer's settled value
            # to the new smoothed value — a true per-sample continuous transition.
            gain_prev = self.master_gain_current
            # Asymmetric smoothing: when voices join, gain must drop immediately to
            # prevent the mixed signal from overdriving tanh during the attack transient.
            # When voices release, gain rises slowly to avoid a sudden loudness jump.
            # This mirrors the compressor attack/release pattern: fast attack, slow release.
            if self.master_gain_target < self.master_gain_current:
                # More voices joined — snap gain down to target this buffer.
                self.master_gain_current = self.master_gain_target
            else:
                # Voices releasing — smooth gain up slowly (~20 buffers ≈ 220 ms).
                self.master_gain_current = self.master_gain_current * 0.95 + self.master_gain_target * 0.05
            # Per-sample gain ramp: eliminates the buffer-boundary step discontinuity
            # that caused clicks when active_count changed between buffers.
            # Built from pre-allocated buffers — no malloc in the hot path.
            gain_ramp = self._cb_gain_ramp[:frame_count]
            _gr_step = (self.master_gain_current - gain_prev) / max(1, frame_count - 1)
            np.multiply(self._cb_indices[:frame_count], _gr_step, out=gain_ramp)
            gain_ramp += gain_prev

            for vi, v in enumerate(self.voices):
                if v.note_active or v.is_releasing:
                    # Smooth velocity to prevent attack peaks when notes change
                    if abs(v.velocity_current - v.velocity_target) > 0.001:
                        v.velocity_current = (v.velocity_current * self.velocity_smoothing
                                            + v.velocity_target * (1.0 - self.velocity_smoothing))
                    else:
                        v.velocity_current = v.velocity_target
                    v.velocity = v.velocity_current  # Update the velocity used in envelope/filter calculations

                    p1_s, p2_s = v.phase, v.phase2

                    # Portamento glide: smoothly interpolate v.frequency from the
                    # source pitch toward base_frequency using exponential (log-linear)
                    # interpolation.  Equal-tempered intervals all take the same time
                    # regardless of size.  Updating v.frequency (not just f1) ensures
                    # the key-tracking filter cutoff also glides in sync, eliminating
                    # the abrupt coefficient jump that causes resonance spikes on note changes.
                    if v._glide_from_freq > 0.0 and v.base_frequency:
                        _glide_dur = max(1, int(self.portamento_time * self.sample_rate))
                        _t = min(1.0, v._glide_elapsed / _glide_dur)
                        # Exponential interpolation in frequency space = linear in semitones
                        v.frequency = v._glide_from_freq * (v.base_frequency / v._glide_from_freq) ** _t
                        v._glide_elapsed += frame_count
                        if v._glide_elapsed >= _glide_dur:
                            v._glide_from_freq = 0.0
                            v.frequency = v.base_frequency

                    f1 = v.frequency * vco_lfo if v.frequency else 440.0
                    if self.octave_enabled and self.octave != 0: f1 *= (2.0 ** self.octave)

                    # Generate primary oscillator with optional 4× oversampling.
                    # Pass pre-allocated voice buffers (_v_osc_buf for waveform output,
                    # _v_phase_arr for phase accumulation) to avoid malloc in hot path.
                    oversample_factor = self.OVERSAMPLE_FACTOR if self.ENABLE_OVERSAMPLING else 1
                    s1, v.phase = self._generate_waveform(
                        self.waveform, f1, frame_count, p1_s,
                        oversample_factor=oversample_factor,
                        _out=v._v_osc_buf, _phases=v._v_phase_arr)

                    # Downsample oscillator output from 192 kHz to 48 kHz if oversampling enabled.
                    # Noise waveforms skip oversampling in _generate_waveform (they return
                    # frame_count samples, not frame_count * oversample_factor), so only
                    # downsample when the signal is actually at the oversampled length.
                    if self.ENABLE_OVERSAMPLING and len(s1) == frame_count * oversample_factor:
                        s1 = self._downsample_polyphase_signal(s1, self.OVERSAMPLE_FACTOR, history=v._oversample_history)

                    # Pre-gate: S-curve fade-in for MONO/UNISON.  Applied between oscillator
                    # and filter so the filter sees a smoothly changing input level.
                    # Shape: (1 - cos(π·t)) / 2 gives zero slope at both endpoints —
                    # no instantaneous amplitude steps at start or finish.
                    # On voice steal, pre_gate_progress is inherited from the outgoing
                    # voice so rapid re-triggers (key bounce, half-pressed contact) do NOT
                    # reset the ramp back to zero and produce a stutter.  On first trigger
                    # from silence, progress starts at 0.0 and ramps to 1.0 over 30ms.
                    # Default progress=1.0 = fully open, no processing overhead.
                    if (self.voice_type in ("mono", "unison")
                            and v.pre_gate_progress < 1.0):
                        _GATE_RAMP_S = 0.030 * self.sample_rate  # 30ms in samples
                        _rate = 1.0 / _GATE_RAMP_S
                        _prog_start = v.pre_gate_progress
                        _prog_end = min(1.0, _prog_start + _rate * frame_count)
                        # Allocation-free pre-gate ramp using shared ramp buffers.
                        # _cb_ramp_buf holds the linear progress array [start, end].
                        # _cb_ramp_cos holds the S-curve intermediate (cos computation).
                        _prog_arr = self._fill_linspace(
                            self._cb_ramp_buf, _prog_start, _prog_end, frame_count)
                        np.clip(_prog_arr, 0.0, 1.0, out=_prog_arr)
                        # S-curve: (1 - cos(π·t)) / 2 — zero slope at both endpoints.
                        # Compute in-place: _cb_ramp_cos = cos(π * _prog_arr), then derive.
                        np.multiply(_prog_arr, np.float32(np.pi), out=self._cb_ramp_cos[:frame_count])
                        np.cos(self._cb_ramp_cos[:frame_count], out=self._cb_ramp_cos[:frame_count])
                        _gate = self._cb_ramp_cos[:frame_count]
                        _gate *= np.float32(-0.5)
                        _gate += np.float32(0.5)
                        v.pre_gate_progress = _prog_end
                        s1 = s1 * _gate

                    # Sine sub-oscillator mixed pre-filter so it's shaped by the
                    # filter (and Filter EG) alongside the primary oscillator.
                    if self.sine_mix > 0:
                        ss, v.sine_phase = self._generate_waveform(
                            "pure_sine", f1, frame_count, v.sine_phase,
                            oversample_factor=oversample_factor,
                            _out=v._v_osc_buf_sin, _phases=v._v_phase_arr)
                        if self.ENABLE_OVERSAMPLING and len(ss) == frame_count * oversample_factor:
                            ss = self._downsample_polyphase_signal(ss, self.OVERSAMPLE_FACTOR, history=v._oversample_history_sine)
                        s1 = s1 + ss * self.sine_mix

                    # Feature 3: Capacitor waveshaper — leaky integrator applied to
                    # the oscillator output at 7% wet blend. At low pitches the
                    # capacitor charges fully each cycle (near-identity). At high
                    # pitches it barely moves, softening transient peaks. Models the
                    # frequency-dependent waveshaping of a series capacitor in the
                    # signal path of a real analog circuit.
                    if v.frequency:
                        _alpha_ws = min(0.92, 2.0 * math.pi * v.frequency / self.sample_rate * self._CAP_WS_RC)
                        _cap_s    = v.cap_ws_state
                        _ws_out   = v._v_cap_ws_buf[:frame_count]
                        for _k in range(frame_count):
                            _cap_s    += _alpha_ws * (float(s1[_k]) - _cap_s)
                            _ws_out[_k] = _cap_s
                        v.cap_ws_state = _cap_s
                        s1 = s1 * (1.0 - self._CAP_WS_BLEND) + _ws_out * self._CAP_WS_BLEND

                    # Filter EG: compute per-buffer scalar and add to vcf_lfo modulation.
                    # feg_value is 0→1; scaled by feg_amount×_FEG_MAX_SWEEP_HZ and added
                    # to the base cutoff inside _apply_filter via cutoff_mod offset.
                    # When feg_amount==0.0 _compute_feg_value fast-paths to 0.0 with no overhead.
                    feg_val = self._compute_feg_value(v, frame_count)
                    feg_cutoff_offset = self.feg_amount * self._FEG_MAX_SWEEP_HZ * feg_val
                    # Pass as a combined modulator: vcf_lfo handles LFO ratio, FEG adds Hz offset.
                    # _apply_filter receives cutoff_mod as a multiplier; we encode the offset by
                    # adjusting the target cutoff temporarily per-voice via a local variable.
                    # Noise blend pre-filter: pink noise summed into the oscillator signal
                    # before the VCF so the filter shapes the noise alongside the tone.
                    # Real analog synths route the noise source into the VCF; this gives
                    # the noise breath and musicality instead of harsh full-bandwidth hiss.
                    # Pink noise (1/f spectrum) has rolled-off highs; much warmer than white.
                    # Square-root curve on the mix keeps low values subtle (analog noise floor
                    # character) while still allowing aggressive sweeps at higher settings.
                    if self.noise_level_current > 0:
                        noise_gain = math.sqrt(self.noise_level_current) * 0.25
                        pink = self._generate_pink_noise(frame_count)
                        s1 = s1 + pink * noise_gain

                    _base_cutoff = self.cutoff_current
                    self.cutoff_current = float(np.clip(_base_cutoff + feg_cutoff_offset, 20.0, 20000.0))
                    s1 = self._sanitize_signal(self._apply_filter(v, s1, rank=1, cutoff_mod=vcf_lfo))
                    self.cutoff_current = _base_cutoff  # restore immediately after filter call

                    if self.rank2_enabled:
                        f2 = f1 * (2.0 ** (self.rank2_detune / 1200.0))
                        s2, v.phase2 = self._generate_waveform(
                            self.rank2_waveform, f2, frame_count, p2_s,
                            oversample_factor=oversample_factor,
                            _out=v._v_osc_buf_r2, _phases=v._v_phase_arr)

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

                    v_samples = self._apply_envelope(
                        v, v_samples, frame_count,
                        _env_buf=v._v_env_buf, _times_buf=v._v_times_buf) * vca_lfo
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
                        # Use pre-allocated onset ramp buffer.
                        # Default value is 1.0 (flat); only the first n samples need updating.
                        ramp = v._v_onset_ramp[:frame_count]
                        ramp.fill(1.0)
                        # Feature 4: RC gate curve — exponential RC charge shape
                        # replaces the linear ramp. Models a capacitor on the gate
                        # signal: fast initial rise then gradual approach to 1.0,
                        # characteristic of real analog gate circuitry.
                        _t_arr = np.linspace(v.onset_samples / ONSET_RAMP,
                                             min((v.onset_samples + n) / ONSET_RAMP, 1.0),
                                             n, dtype=np.float32)
                        ramp[:n] = 1.0 - np.exp(-_t_arr / self._CAP_GATE_TAU)
                        ramp[:n] /= np.float32(1.0 - math.exp(-1.0 / self._CAP_GATE_TAU))
                        v_samples = v_samples * ramp
                        v.onset_samples += frame_count
                    v_samples = self._apply_dc_blocker(v, v_samples)
                    if self.voice_type == "unison":
                        # Map each voice's detune position to the stereo field.
                        # Voice index 0 = most negative detune → full left (pan=0.0).
                        # Voice index N-1 = most positive detune → full right (pan=1.0).
                        # This links pitch position to spatial position, giving the
                        # characteristic "wide sweep" of professional unison sounds.
                        n_v = len(self.voices)
                        unison_pan = vi / max(n_v - 1, 1)
                        ang = unison_pan * np.pi / 2
                        # 1/sqrt(N) normalization: detuned voices are partially decorrelated
                        # (different phases + beating), so RMS sum grows as sqrt(N), not N.
                        # 1/N was too quiet; 1/sqrt(N) gives perceptually consistent loudness
                        # whether 2 or 8 voices are stacked.
                        mix_scale = 1.0 / math.sqrt(self.num_voices)
                    else:
                        ang = v.pan * np.pi / 2
                        mix_scale = 1.0
                    mixed_l += v_samples * np.cos(ang) * mix_scale
                    mixed_r += v_samples * np.sin(ang) * mix_scale

            # Ghost voice mix: draining release tails from promoted-but-stolen voices.
            # Ghost voices run the same signal chain as real voices but output at a
            # reduced gain (0.7×) and are never counted in the gain normalisation.
            # Pan uses centre (ang=π/4) so ghost tails are not spatially distracting.
            _GHOST_GAIN = 0.7
            _ghost_ang  = np.pi / 4.0   # centre pan
            for g in self._ghost_voices:
                if g.is_ghost and (g.note_active or g.is_releasing):
                    f_g = g.frequency if g.frequency else 440.0
                    if self.octave_enabled and self.octave != 0:
                        f_g *= (2.0 ** self.octave)
                    oversample_factor = self.OVERSAMPLE_FACTOR if self.ENABLE_OVERSAMPLING else 1
                    gs, g.phase = self._generate_waveform(self.waveform, f_g, frame_count, g.phase, oversample_factor=oversample_factor)
                    if self.ENABLE_OVERSAMPLING and len(gs) == frame_count * oversample_factor:
                        gs = self._downsample_polyphase_signal(gs, self.OVERSAMPLE_FACTOR, history=g._oversample_history)
                    gs = self._sanitize_signal(self._apply_filter(g, gs))
                    gs = self._sanitize_signal(self._apply_envelope(g, gs, frame_count,
                                                                     _env_buf=g._v_env_buf,
                                                                     _times_buf=g._v_times_buf))
                    ONSET_RAMP = int(self.sample_rate * g.onset_ms / 1000.0)
                    if g.onset_samples < ONSET_RAMP:
                        n = min(frame_count, ONSET_RAMP - g.onset_samples)
                        ramp = g._v_onset_ramp[:frame_count]
                        ramp.fill(1.0)
                        # Feature 4: RC gate curve (ghost voice path — same formula).
                        _t_arr = np.linspace(g.onset_samples / ONSET_RAMP,
                                             min((g.onset_samples + n) / ONSET_RAMP, 1.0),
                                             n, dtype=np.float32)
                        ramp[:n] = 1.0 - np.exp(-_t_arr / self._CAP_GATE_TAU)
                        ramp[:n] /= np.float32(1.0 - math.exp(-1.0 / self._CAP_GATE_TAU))
                        gs[:n] = gs[:n] * ramp[:n]
                        g.onset_samples += frame_count
                    gs = self._apply_dc_blocker(g, gs)
                    mixed_l += gs * np.cos(_ghost_ang) * _GHOST_GAIN
                    mixed_r += gs * np.sin(_ghost_ang) * _GHOST_GAIN

            # ── BBD-style Chorus (bypass when chorus_mix == 0) ───────────────
            # All taps read from the same shared ring buffer. Four LFO phases
            # spaced 90° apart (set at init) advance every sample by
            # 2π * chorus_rate / sample_rate so the modulation is continuous
            # across buffer boundaries. Base delay 0.5ms + depth-modulated swing
            # up to ±25ms. wet/dry mix controls the blend.
            if self.ENABLE_CHORUS and self.chorus_mix > 0.0:
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
                # Tier 2: compute write positions into pre-allocated int32 buffer.
                # Replaces .astype(np.int32) which created a fresh 480-element array.
                np.add(float(self._chorus_write), idx_fc, out=self._cb_idx_f[:frame_count])
                np.mod(self._cb_idx_f[:frame_count], float(buf_len), out=self._cb_idx_f[:frame_count])
                self._cb_cho_wr_idx[:frame_count] = self._cb_idx_f[:frame_count]
                write_pos = self._cb_cho_wr_idx[:frame_count]
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
            if self.ENABLE_DELAY and self.delay_mix > 0.0:
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
                    # Tier 2: pre-allocated int32 array for delay write positions.
                    np.add(float(self._delay_write), idx_fc, out=self._cb_idx_f[:frame_count])
                    np.mod(self._cb_idx_f[:frame_count], float(buf_len), out=self._cb_idx_f[:frame_count])
                    self._cb_dly_wr_idx[:frame_count] = self._cb_idx_f[:frame_count]
                    write_pos = self._cb_dly_wr_idx[:frame_count]
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
                ramp = self._fill_linspace(self._cb_ramp_buf, ramp_start, ramp_end, frame_count)
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
                ramp = self._fill_linspace(self._cb_ramp_buf, ramp_start, ramp_end, frame_count)
                mixed_l *= ramp
                mixed_r *= ramp
                self._mute_ramp_remaining = max(0, self._mute_ramp_remaining - frame_count)
                if self._mute_ramp_remaining == 0:
                    if self._pending_all_notes_off:
                        # Mode-switch path: silence all voices at the bottom of the
                        # fade, then stop. No fade-in — new mode starts from silence.
                        for v in self.voices:
                            v.reset()
                        for g in self._ghost_voices:
                            g.reset()
                        self._arp_held_notes.clear(); self._arp_sequence.clear()
                        self._arp_note_playing = None; self._arp_sample_counter = 0
                        self._fx_tail_samples = 0
                        self._pending_all_notes_off = False
                    else:
                        self._mute_ramp_fadein = self._MUTE_RAMP_LEN  # arm fade-in

            if self._mute_ramp_fadein > 0:
                ramp_start = 1.0 - (self._mute_ramp_fadein / self._MUTE_RAMP_LEN)
                ramp_end   = 1.0 - max(0, self._mute_ramp_fadein - frame_count) / self._MUTE_RAMP_LEN
                ramp = self._fill_linspace(self._cb_ramp_buf, ramp_start, ramp_end, frame_count)
                mixed_l *= ramp
                mixed_r *= ramp
                self._mute_ramp_fadein = max(0, self._mute_ramp_fadein - frame_count)

            # Waveform saturation ceiling: controls how early the tanh soft-clips.
            # Square has high RMS relative to peak so its ceiling is lower (less headroom
            # = more compression at the same drive level, taming harshness).
            # Sine/pure_sine get a ceiling of 0.95 — slightly below saw unity (1.0) to
            # give sine a marginally softer saturation knee, while staying close enough
            # in level that the difference is inaudible at normal drive settings.
            # Saw and triangle are at unity (1.0); same RMS, same saturation character.
            comp = 0.95 if self.waveform in ["sine", "pure_sine"] else (0.75 if self.waveform == "square" else 1.0)

            # Perceptual loudness compensation for octave position.
            # Low octaves (32', 16') lose perceived punch due to the ear's reduced
            # sensitivity at low frequencies (equal-loudness / Fletcher-Munson effect).
            # A small pre-tanh gain boost compensates. Applied before drive so the
            # boost feeds naturally into the saturation curve at high drive values,
            # adding warmth rather than just raw level. Higher octaves (4', 2') are
            # already bright and perceived as louder — no compensation needed.
            _OCTAVE_COMP = {-2: 1.25, -1: 1.12, 0: 1.0, 1: 1.0, 2: 1.0}
            octave_comp = _OCTAVE_COMP.get(self.octave, 1.0)

            # Mix metronome clicks into the synth signal BEFORE saturation.
            # This ensures they go through the normal tanh curve and are never lost
            # to clipping. The clicks are audible even with high synth levels.
            if self._metro_click_buf is not None and self._metro_click_pos < len(self._metro_click_buf):
                remaining = len(self._metro_click_buf) - self._metro_click_pos
                n_click = min(frame_count, remaining)
                chunk = self._metro_click_buf[self._metro_click_pos:self._metro_click_pos + n_click]
                mixed_l[:n_click] += chunk
                mixed_r[:n_click] += chunk
                self._metro_click_pos += n_click
                if self._metro_click_pos >= len(self._metro_click_buf):
                    self._metro_click_buf = None

            # Voice-count gain ramp normalises poly voice sum, then tanh soft-clips
            # at ±ceiling. filter_drive (applied post-ladder per voice) pushes the
            # mixed signal above the ceiling, causing progressive saturation.
            # At drive=1.0 the signal sits well below ceiling — gentle saturation.
            # Saturation ceiling is fixed at comp (waveform RMS compensation only).
            # amp_level is applied as a post-tanh linear gain so that changing the amp
            # knob only scales loudness — it never reshapes the tanh saturation curve,
            # which would cause audible waveform-character artifacts mid-note.
            ceiling = max(comp, 0.01)
            mixed_l *= gain_ramp
            mixed_r *= gain_ramp
            mixed_l *= octave_comp
            mixed_r *= octave_comp
            # Makeup gain: constant-power stereo panning (cos/sin at 45°) costs
            # ~3 dB per channel on centre-panned voices.  Combined with conservative
            # per-voice normalization this leaves roughly -8 dBFS of headroom unused
            # at normal playing levels.  A pre-saturation boost of 1.4× (~+3 dB)
            # fills that headroom while letting the tanh work a little harder for
            # natural analog warmth.  Applied before drive so high-drive presets
            # are unaffected (tanh already saturates fully at drive >= 2).
            _MAKEUP_GAIN = 1.4
            mixed_l *= _MAKEUP_GAIN
            mixed_r *= _MAKEUP_GAIN
            # Drive applied here — after _sanitize_signal has already guarded per-voice
            # filter output. Multiplying the summed mix by filter_drive pushes the signal
            # above ceiling into tanh saturation. drive=1.0 leaves the signal near the
            # linear region (gentle warmth). drive=8.0 pushes it 8× above ceiling,
            # producing heavy clipping and rich odd/even harmonics.
            mixed_l *= self.filter_drive_current
            mixed_r *= self.filter_drive_current
            mixed_l = np.tanh(mixed_l / ceiling) * ceiling * self.amp_level_current * self.master_volume
            mixed_r = np.tanh(mixed_r / ceiling) * ceiling * self.amp_level_current * self.master_volume

            # Engine-level inter-buffer crossfade: blend from the last buffer's final
            # post-tanh output toward the new output over _TRANSITION_XF_SAMPLES samples.
            # This hides FIR frequency-change transients at MONO/UNISON note transitions.
            # Applied post-tanh so _last_output_L/R stores the actual output value —
            # guarantees exact sample-0 continuity regardless of drive or gain_ramp changes.
            if self._transition_xf_remaining > 0:
                n_xf = min(self._transition_xf_remaining, frame_count)
                p = self._fill_linspace(self._cb_ramp_buf,
                                        0.0, float(n_xf) / self._TRANSITION_XF_SAMPLES, n_xf)
                mixed_l[:n_xf] = self._last_output_L * (1.0 - p) + mixed_l[:n_xf] * p
                mixed_r[:n_xf] = self._last_output_R * (1.0 - p) + mixed_r[:n_xf] * p
                self._transition_xf_remaining -= n_xf
            # Tier 3: in-place clip — avoids creating two new 480-element arrays per buffer.
            # mixed_l/mixed_r already live in pre-allocated _cb_mixed_l/r; clip to ±1 in-place.
            np.clip(mixed_l, -1.0, 1.0, out=mixed_l)
            np.clip(mixed_r, -1.0, 1.0, out=mixed_r)
            clipped_l = mixed_l
            clipped_r = mixed_r

            # Mix metronome click into the output after saturation/clipping so
            # it always sounds clean and is not coloured by the synth signal chain.
            if self._metro_click_buf is not None and self._metro_click_pos < len(self._metro_click_buf):
                remaining = len(self._metro_click_buf) - self._metro_click_pos
                n_click = min(frame_count, remaining)
                chunk = self._metro_click_buf[self._metro_click_pos:self._metro_click_pos + n_click]
                clipped_l[:n_click] = np.clip(clipped_l[:n_click] + chunk, -1.0, 1.0)
                clipped_r[:n_click] = np.clip(clipped_r[:n_click] + chunk, -1.0, 1.0)
                self._metro_click_pos += n_click
                if self._metro_click_pos >= len(self._metro_click_buf):
                    self._metro_click_buf = None

            # --- Output transformer: one-pole 18 kHz LP + even harmonic ---
            # The LP softens extreme highs (analog output transformer roundness).
            # Even harmonic x += k*x² injects 2nd harmonic warmth with no per-
            # sample Python loop: scipy lfilter fast path (C/GIL-free) when
            # available; scalar ARM fallback otherwise. Pre-allocated _xfmr_sq_buf
            # avoids temporary array creation on the hot path.
            _fc = frame_count
            if self._scipy_lfilter is not None:
                _tl, self._XFMR_LP_ZI_L = self._scipy_lfilter(
                    self._XFMR_LP_B, self._XFMR_LP_A,
                    clipped_l[:_fc].astype(np.float64), zi=self._XFMR_LP_ZI_L)
                clipped_l[:_fc] = _tl.astype(np.float32)
                _tr, self._XFMR_LP_ZI_R = self._scipy_lfilter(
                    self._XFMR_LP_B, self._XFMR_LP_A,
                    clipped_r[:_fc].astype(np.float64), zi=self._XFMR_LP_ZI_R)
                clipped_r[:_fc] = _tr.astype(np.float32)
            else:
                # Scalar loop for ARM / no-scipy. 512 iters, no allocation.
                _xc  = -float(self._XFMR_LP_A[1])
                _xg  = 1.0 - _xc
                _xsl = float(self._XFMR_LP_ZI_L[0])
                _xsr = float(self._XFMR_LP_ZI_R[0])
                for _xi in range(_fc):
                    _xsl = _xg * clipped_l[_xi] + _xc * _xsl
                    _xsr = _xg * clipped_r[_xi] + _xc * _xsr
                    clipped_l[_xi] = _xsl
                    clipped_r[_xi] = _xsr
                self._XFMR_LP_ZI_L[0] = _xsl
                self._XFMR_LP_ZI_R[0] = _xsr
            # Even harmonic: x += k*x² — pre-alloc buf reused for both channels.
            _sq = self._xfmr_sq_buf[:_fc]
            np.multiply(clipped_l[:_fc], clipped_l[:_fc], out=_sq)
            clipped_l[:_fc] += self._XFMR_EVEN * _sq
            np.multiply(clipped_r[:_fc], clipped_r[:_fc], out=_sq)
            clipped_r[:_fc] += self._XFMR_EVEN * _sq
            np.clip(clipped_l[:_fc], -1.0, 1.0, out=clipped_l[:_fc])
            np.clip(clipped_r[:_fc], -1.0, 1.0, out=clipped_r[:_fc])

            # --- Tube compressor: warm RMS compression at the output ---
            # Per-buffer RMS via np.dot (BLAS, zero temp allocation) drives a
            # scalar envelope follower and gain computer — no per-sample work.
            # 2nd harmonic injection (x += k2*x²) scales with gain reduction so
            # warmth is audible only when the compressor is actively squashing.
            _dot_sum = (float(np.dot(clipped_l[:_fc], clipped_l[:_fc])) +
                        float(np.dot(clipped_r[:_fc], clipped_r[:_fc])))
            _rms = math.sqrt(_dot_sum * (0.5 / _fc))
            if _rms > self._comp_env:
                self._comp_env += self._COMP_ENV_ATK * (_rms - self._comp_env)
            else:
                self._comp_env += self._COMP_ENV_REL * (_rms - self._comp_env)
            _env = max(self._comp_env, 1e-6)
            _gtgt = (((self._COMP_THRESH / _env) ** self._COMP_RATIO_EXP)
                     if _env > self._COMP_THRESH else 1.0)
            if _gtgt < self._comp_gain:
                self._comp_gain += self._COMP_GAIN_ATK * (_gtgt - self._comp_gain)
            else:
                self._comp_gain += self._COMP_GAIN_REL * (_gtgt - self._comp_gain)
            _fg = self._comp_gain * self._COMP_MAKEUP
            clipped_l[:_fc] *= _fg
            clipped_r[:_fc] *= _fg
            # 2nd harmonic: only active during compression — gate prevents overhead
            # on silence or quiet passages where comp_gain stays near 1.0.
            if self._comp_gain < 0.98:
                _k2 = (1.0 - self._comp_gain) * self._COMP_HARMONIC
                np.multiply(clipped_l[:_fc], clipped_l[:_fc], out=_sq)
                clipped_l[:_fc] += _k2 * _sq
                np.multiply(clipped_r[:_fc], clipped_r[:_fc], out=_sq)
                clipped_r[:_fc] += _k2 * _sq
                np.clip(clipped_l[:_fc], -1.0, 1.0, out=clipped_l[:_fc])
                np.clip(clipped_r[:_fc], -1.0, 1.0, out=clipped_r[:_fc])

            self._last_output_L = float(clipped_l[-1])
            self._last_output_R = float(clipped_r[-1])

            # Cache VU meter levels for visualizer (thread-safe float write).
            # Max amplitude of this buffer for left/right channels.
            self.level_l = float(np.max(np.abs(clipped_l)))
            self.level_r = float(np.max(np.abs(clipped_r)))
            if self._level_shm is not None:
                struct.pack_into('ff', self._level_shm.buf, 0, self.level_l, self.level_r)
                # Write mono-mix samples into the circular waveform buffer.
                # Layout: bytes 8-11 = write_pos (i32), bytes 12+ = 2048 x f32 samples.
                _WF_N = 2048
                mono = ((clipped_l + clipped_r) * 0.5).astype(np.float32)
                n = len(mono)
                wp = struct.unpack_from('i', self._level_shm.buf, 8)[0]
                wf_arr = np.ndarray((_WF_N,), dtype=np.float32,
                                    buffer=self._level_shm.buf, offset=12)
                end = wp + n
                if end <= _WF_N:
                    wf_arr[wp:end] = mono
                else:
                    first = _WF_N - wp
                    wf_arr[wp:] = mono[:first]
                    wf_arr[:end - _WF_N] = mono[first:]
                struct.pack_into('i', self._level_shm.buf, 8, end % _WF_N)

            # TPDF dither (airwindows-inspired independent channel design).
            # One double-length random buffer per channel; first half is r1,
            # second half r2.  noise = (r1 - r2) * AMP has triangular
            # distribution on (-AMP, +AMP) = one 16-bit LSB width.
            # Two generator calls instead of four — see __init__ comment.
            fc = frame_count
            buf_l = self._dither_buf_l[:2 * fc]
            buf_r = self._dither_buf_r[:2 * fc]
            self._dither_rng_l.random(2 * fc, dtype=np.float32, out=buf_l)
            self._dither_rng_r.random(2 * fc, dtype=np.float32, out=buf_r)
            dither_l = (buf_l[:fc] - buf_l[fc:]) * self._DITHER_AMP
            dither_r = (buf_r[:fc] - buf_r[fc:]) * self._DITHER_AMP
            outdata[:fc, 0] = np.clip(clipped_l + dither_l, -1.0, 1.0)
            outdata[:fc, 1] = np.clip(clipped_r + dither_r, -1.0, 1.0)

            if _arm_probe:
                _cb_ms = (self._perf_counter() - _cb_t0) * 1000.0
                _deadline_ms = frame_count / self.sample_rate * 1000.0
                if _cb_ms > _deadline_ms * 0.5:
                    self._arm_slow_cb_count += 1
        except Exception:
            import traceback; traceback.print_exc()
            outdata.fill(0)

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

    def get_arm_diagnostics(self):
        """Return ARM audio health counters as (xruns, slow_callbacks, total_callbacks).

        All values are zero on non-ARM platforms. Safe to call from the UI thread.
        """
        if not self._IS_ARM:
            return (0, 0, 0)
        return (self._arm_xrun_count, self._arm_slow_cb_count, self._arm_cb_count)

    def close(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def is_available(self) -> bool: return AUDIO_AVAILABLE and self.running

    def warm_up(self):
        if not self.is_available():
            return
        if self._IS_ARM:
            import time as _time
            # Pre-heat all voice code paths so the user's first note plays
            # without a stutter. On ARM, first-run numpy/scipy setup adds
            # 50-100 ms per voice. Cycling through all voices at very low
            # velocity here forces that work to happen before the UI loads.
            for i in range(self.num_voices):
                self.note_on(60 + i, 8)
            _time.sleep(0.30)   # ~6 buffers at 2048/44100 = ~276 ms budget
            self.all_notes_off()
            _time.sleep(0.08)   # let release tails drain
        else:
            self.note_on(60, 1)
            self.note_off(60)
