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

        # Phase offset for polyphonic spread
        self.phase_offset = (voice_index * np.pi / 4.0) % (2 * np.pi)
        pan_positions = [0.40, 0.60, 0.45, 0.55, 0.48, 0.52, 0.49, 0.51]
        self.pan = pan_positions[voice_index] if voice_index < len(pan_positions) else 0.5

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

        # RESET filter/DC memory ONLY if starting from silence
        if was_silent:
            self.filter_state_lpf1 = self.filter_state_hpf1 = 0.0
            self.filter_state_lpf2 = self.filter_state_hpf2 = 0.0
            self.dc_blocker_x = self.dc_blocker_y = 0.0
            # Note: self.phase is NOT reset here (Free-Running)

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
            except Exception as e:
                print(f"Audio initialization failed: {e}")
                self.running = False

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
        if waveform == "pure_sine": samples = np.sin(phases)
        elif waveform == "sine":
            saw = 2.0 * t_norm - 1.0
            x = saw * np.pi
            sine_shaped = x - (x**3) / 6.0 + (x**5) / 120.0
            samples = sine_shaped * 0.98 + saw * 0.02
        elif waveform == "triangle": samples = 4.0 * np.abs(t_norm - 0.5) - 1.0
        elif waveform == "square": samples = np.where(np.sin(phases) >= 0, 1.0, -1.0)
        else: samples = 2.0 * t_norm - 1.0
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
            rel_mod = 1.0 / (0.5 + voice.release_velocity)
            time_const = max(0.005, (self.release * rel_mod) / 4.0)
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
            ANTI_I = 0.002
            if times[0] < ANTI_I:
                mask = times < ANTI_I
                envelope[mask] *= (1.0 - np.exp(-10.0 * (times[mask]/ANTI_I)))
            if voice.steal_start_level > 0.001:
                CROSS = 0.003
                if times[0] < CROSS:
                    mask = times < CROSS
                    p = 1.0 - np.exp(-8.0 * (times[mask]/CROSS))
                    envelope[mask] = voice.steal_start_level * (1.0 - p) + envelope[mask] * p
                    if times[-1] >= CROSS: voice.steal_start_level = 0.0
            dec_end = self.attack + self.decay
            dec_mask = (times >= self.attack) & (times < dec_end)
            if self.decay > 0:
                p = (times[dec_mask] - self.attack) / self.decay
                envelope[dec_mask] = v_int * (1.0 - p * (1.0 - self.sustain))
            else: envelope[dec_mask] = v_int * self.sustain
            envelope[times >= dec_end] = v_int * self.sustain
            voice.envelope_time = times[-1] + dt
        voice.last_envelope_level = envelope[-1]
        return samples * envelope

    def _filter_process(self, samples: np.ndarray, cutoff: float, filter_type: str, prev_state: float, res: float = 0.0) -> tuple[np.ndarray, float]:
        alpha = np.clip(2 * np.pi * cutoff / self.sample_rate, 0.0, 1.0)
        res_fb = res * 0.9
        b, a = np.array([alpha], dtype=np.float32), np.array([1.0, -(1.0 - alpha + alpha * res_fb)], dtype=np.float32)
        try:
            from scipy import signal
            out, zi = signal.lfilter(b, a, samples, zi=[prev_state])
            return (out if filter_type == "lpf" else samples - out), zi[0]
        except ImportError:
            filtered = np.zeros_like(samples)
            state, a1_comp = prev_state, (1.0 - alpha + alpha * res_fb)
            for i in range(len(samples)):
                state = alpha * samples[i] + a1_comp * state
                filtered[i] = state if filter_type == "lpf" else samples[i] - state
            return filtered, state

    def _apply_filter(self, voice: Voice, samples: np.ndarray, rank: int = 1, cutoff_mod: float = 1.0) -> np.ndarray:
        lpf_s = voice.filter_state_lpf1 if rank == 1 else voice.filter_state_lpf2
        hpf_s = voice.filter_state_hpf1 if rank == 1 else voice.filter_state_hpf2
        f_oct = voice.frequency * (2.0 ** self.octave) if (voice.frequency and self.octave_enabled) else voice.frequency or 440.0
        track_mult = 1.0 + 0.5 * (f_oct / 440.0 - 1.0)
        vel_mult = 0.7 + (voice.velocity * 0.6)
        fl_lpf = np.clip(self.cutoff * cutoff_mod * track_mult * vel_mult, 20.0, 20000.0)
        fl_hpf = np.clip(self.hpf_cutoff * cutoff_mod * track_mult * vel_mult, 20.0, 20000.0)
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
        while not self.midi_event_queue.empty():
            try:
                e = self.midi_event_queue.get_nowait()
                if e['type'] == 'note_on': self._trigger_note(e['note'], e['velocity'])
                elif e['type'] == 'note_off': self._release_note(e['note'], e.get('velocity', 0.5))
            except: break

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
        if best_v: best_v.trigger(note, freq, vel)

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
            vco_lfo, vcf_lfo, vca_lfo = 1.0 + (lfo_val * self.lfo_vco_mod * 0.05), 1.0 + (lfo_val * self.lfo_vcf_mod * 0.5), 1.0 + (lfo_val * self.lfo_vca_mod * 0.3)
            mixed_l, mixed_r, active_count = np.zeros(frame_count, dtype=np.float32), np.zeros(frame_count, dtype=np.float32), 0
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
                    else: v_samples = s1
                    if self.sine_mix > 0:
                        ss, _ = self._generate_waveform("pure_sine", f1, frame_count, p1_s)
                        v_samples += ss * self.sine_mix
                    v_samples = self._apply_envelope(v, v_samples, frame_count) * vca_lfo
                    v_samples = self._apply_dc_blocker(v, v_samples)
                    ang = v.pan * np.pi / 2
                    mixed_l += v_samples * np.cos(ang); mixed_r += v_samples * np.sin(ang)
                    active_count += 1
            if active_count == 0:
                self.master_gain_target = self.master_gain_current = 1.0
                return (np.zeros(frame_count * 2, dtype=np.int16).tobytes(), pyaudio.paContinue)
            self.master_gain_target = 1.0 / np.sqrt(active_count) if active_count > 1 else 1.0
            if self.master_gain_target < self.master_gain_current: self.master_gain_current = self.master_gain_current * 0.5 + self.master_gain_target * 0.5
            else: self.master_gain_current = self.master_gain_current * 0.8 + self.master_gain_target * 0.2
            comp = 1.4 if self.waveform in ["sine", "pure_sine"] else (0.8 if self.waveform == "square" else 1.7)
            final_gain = self.amp_level_current * comp * self.master_gain_current
            mixed_l, mixed_r = np.tanh(mixed_l * final_gain * 0.9), np.tanh(mixed_r * final_gain * 0.9)
            mixed_l, mixed_r = mixed_l * self.master_volume, mixed_r * self.master_volume
            out = np.empty(frame_count * 2, dtype=np.int16)
            out[0::2] = np.clip(mixed_l * 32767, -32767, 32767); out[1::2] = np.clip(mixed_r * 32767, -32767, 32767)
            return (out.tobytes(), pyaudio.paContinue)
        except Exception as e: return (np.zeros(frame_count * 2, dtype=np.int16).tobytes(), pyaudio.paContinue)

    def note_on(self, note: int, velocity: int = 127):
        self.held_notes.add(note)
        self.midi_event_queue.put({'type': 'note_on', 'note': note, 'velocity': velocity / 127.0})

    def note_off(self, note: int, velocity: int = 0):
        self.held_notes.discard(note)
        self.midi_event_queue.put({'type': 'note_off', 'note': note, 'velocity': velocity / 127.0})

    def all_notes_off(self):
        self.held_notes.clear()
        for v in self.voices: v.reset()

    def pitch_bend_change(self, value: int): self.pitch_bend_target = ((value - 8192) / 8192.0) * 2.0

    def modulation_change(self, value: int): self.mod_wheel = value / 127.0

    def update_parameters(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                if k == "amp_level": self.amp_level_target = v
                elif k == "master_volume": self.master_volume_target = v
                else: setattr(self, k, v)

    def close(self):
        self.running = False
        if self.stream: self.stream.stop_stream(); self.stream.close()
        if self.audio: self.audio.terminate()

    def is_available(self) -> bool: return AUDIO_AVAILABLE and self.running

    def warm_up(self):
        if self.is_available(): self.note_on(0, 1); self.note_off(0)
