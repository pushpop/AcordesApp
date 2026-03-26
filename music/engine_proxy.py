# ABOUTME: SynthEngine proxy that runs the audio engine in a separate process.
# ABOUTME: Isolates PyAudio from the Textual UI thread to prevent GIL-caused audio artifacts.

import multiprocessing
import queue
import struct
import threading
from multiprocessing.shared_memory import SharedMemory
from music.preset_manager import DEFAULT_PARAMS


def _audio_process_main(cmd_queue, ready_event, error_event, error_msg_arr, startup_info_arr, level_shm_name, output_device_index=None, buffer_size=1024, audio_backend=None, enable_oversampling=True):
    """Entry point for the audio subprocess.

    Constructs SynthEngine, signals the main process when ready, then
    forwards commands from cmd_queue to the engine until a shutdown
    command is received.

    Runs on Windows via 'spawn', so no inherited state from the parent
    process: all imports happen fresh here.
    """
    try:
        # Import here so only the audio process loads PyAudio/numpy.
        from music.synth_engine import SynthEngine

        engine = SynthEngine(output_device_index=output_device_index, buffer_size=buffer_size, audio_backend=audio_backend, enable_oversampling=enable_oversampling, level_shm_name=level_shm_name)
        engine.warm_up()

        # Write startup diagnostics to the shared array so the LoadingScreen
        # can display them without raw print() calls bleeding into the UI.
        # Use get_obj().raw for bulk assignment: multiprocessing.Array('c', N)
        # wraps a ctypes c_char array whose elements are bytes objects of length
        # 1, not integers — bytes(arr) and element-by-element int assignment both
        # raise TypeError.  get_obj().raw gives direct access to the raw buffer.
        try:
            info = getattr(engine, '_startup_info', '')
            info_bytes = info.encode('utf-8')[:1023]
            padded = info_bytes + b'\x00' * (1024 - len(info_bytes))
            startup_info_arr.get_obj().raw = padded
        except Exception:
            pass

        ready_event.set()

        # Command forwarding loop.  Runs on the subprocess main thread.
        # The audio callback runs on PortAudio's internal C thread, so
        # this loop and the callback only compete for the GIL inside this
        # one process — Textual cannot interfere.
        while True:
            try:
                msg = cmd_queue.get(timeout=0.5)
            except Exception:
                # Queue.Empty or interrupted — check if engine is still running.
                if not engine.running:
                    break
                continue

            if not isinstance(msg, dict):
                continue

            msg_type = msg.get('type', '')

            if msg_type == 'shutdown':
                break
            elif msg_type == 'note_on':
                # Call engine.note_on so held_notes bookkeeping stays correct.
                engine.note_on(msg['note'], msg['velocity'])
            elif msg_type == 'note_off':
                engine.note_off(msg['note'], msg.get('velocity', 0))
            elif msg_type == 'all_notes_off':
                engine.all_notes_off()
            elif msg_type == 'pitch_bend':
                engine.pitch_bend_change(msg['value'])
            elif msg_type == 'modulation':
                engine.modulation_change(msg['value'])
            else:
                # param_update, soft_all_notes_off, mute_gate, drum_trigger
                # go directly to the engine's internal threading.Queue for
                # sample-accurate processing on the audio callback thread.
                engine.midi_event_queue.put(msg)

    except Exception as exc:
        err_bytes = str(exc).encode('utf-8')[:255]
        padded = err_bytes + b'\x00' * (256 - len(err_bytes))
        error_msg_arr.get_obj().raw = padded
        error_event.set()
    finally:
        try:
            engine.close()
        except Exception:
            pass


class SynthEngineProxy:
    """Drop-in replacement for SynthEngine that runs the engine in a child process.

    All method calls are serialized as dicts sent through a multiprocessing.Queue.
    The child process is completely isolated from the Textual GIL, so UI redraws
    (opening modals, mounting screens) cannot cause audio callback deadline misses.

    API compatibility: all methods and attributes used by existing modes are
    implemented here.  No mode code needs to change.
    """

    def __init__(self, output_device_index=None, buffer_size=1024, audio_backend=None,
                 enable_oversampling=True):
        self._output_device_index = output_device_index
        self._buffer_size = buffer_size
        self._audio_backend = audio_backend
        self._enable_oversampling = enable_oversampling
        self._cmd_queue = multiprocessing.Queue()
        self._ready_event = multiprocessing.Event()
        self._error_event = multiprocessing.Event()
        # Shared byte array for error message from child process (256 bytes max).
        self._error_msg_arr = multiprocessing.Array('c', 256)
        # Shared byte array for startup diagnostic info (device, rate, etc.).
        self._startup_info_arr = multiprocessing.Array('c', 1024)

        # Shared memory block for VU meter levels and waveform written by audio subprocess.
        # Layout: [level_l f32][level_r f32][write_pos i32][2048 x f32 waveform samples]
        # Total: 8 + 4 + 2048*4 = 8204 bytes.
        _WAVEFORM_SAMPLES = 2048
        self._level_shm = SharedMemory(create=True, size=8 + 4 + _WAVEFORM_SAMPLES * 4)
        struct.pack_into('ffi', self._level_shm.buf, 0, 0.0, 0.0, 0)

        # Local shadow of engine parameters — updated on every update_parameters()
        # call so get_current_params() can return accurate state without IPC.
        self._shadow_params: dict = dict(DEFAULT_PARAMS)

        # Expose cmd_queue as midi_event_queue so modes that put events directly
        # (e.g. synth_mode's mute_gate) work without modification.
        self.midi_event_queue = self._cmd_queue

        # held_notes mirrors the engine's held set; kept in sync by note_on/off.
        self.held_notes: set = set()

        self._process = multiprocessing.Process(
            target=_audio_process_main,
            args=(
                self._cmd_queue,
                self._ready_event,
                self._error_event,
                self._error_msg_arr,
                self._startup_info_arr,
                self._level_shm.name,
                output_device_index,
                buffer_size,
                audio_backend,
                enable_oversampling,
            ),
            daemon=True,
            name="acordes-audio",
        )
        self._process.start()

    # ── Startup / lifecycle ───────────────────────────────────────

    def wait_ready(self, timeout: float = 15.0) -> bool:
        """Block until the audio process signals ready or timeout expires."""
        return self._ready_event.wait(timeout)

    def get_error(self) -> str:
        """Return error message from child process, or empty string if none."""
        if self._error_event.is_set():
            raw = self._error_msg_arr.get_obj().raw.split(b'\x00')[0]
            return raw.decode('utf-8', errors='replace')
        return ""

    def get_startup_info(self) -> str:
        """Return startup diagnostic string written by the child process.

        Populated after is_available() returns True. Empty string on desktop
        builds (diagnostics are only collected on ARM).
        """
        raw = self._startup_info_arr.get_obj().raw.split(b'\x00')[0]
        return raw.decode('utf-8', errors='replace')

    def is_available(self) -> bool:
        return self._ready_event.is_set() and self._process.is_alive()

    def warm_up(self):
        """No-op: the audio process warms up automatically after construction."""
        pass

    def close(self):
        """Shut down the audio process cleanly."""
        try:
            self._cmd_queue.put({'type': 'shutdown'})
        except Exception:
            pass
        self._process.join(timeout=3.0)
        if self._process.is_alive():
            self._process.terminate()
        try:
            self._level_shm.close()
            self._level_shm.unlink()
        except Exception:
            pass

    def restart_with_device(self, output_device_index):
        """Shut down the current audio process and start a new one with a different device.

        Resets the ready/error events and replaces the subprocess.
        Caller must wait for is_available() before sending commands.
        """
        self.close()
        self._output_device_index = output_device_index
        self._cmd_queue = multiprocessing.Queue()
        self.midi_event_queue = self._cmd_queue
        self._ready_event = multiprocessing.Event()
        self._error_event = multiprocessing.Event()
        self._error_msg_arr = multiprocessing.Array('c', 256)
        self._startup_info_arr = multiprocessing.Array('c', 1024)
        self.held_notes.clear()

        self._process = multiprocessing.Process(
            target=_audio_process_main,
            args=(
                self._cmd_queue,
                self._ready_event,
                self._error_event,
                self._error_msg_arr,
                self._startup_info_arr,
                self._level_shm.name,
                output_device_index,
                self._buffer_size,
                self._audio_backend,
                self._enable_oversampling,
            ),
            daemon=True,
            name="acordes-audio",
        )
        self._process.start()

    def restart_with_oversampling(self, enable_oversampling: bool):
        """Shut down and restart with oversampling enabled or disabled."""
        self._enable_oversampling = enable_oversampling
        self.restart_with_device(self._output_device_index)

    def restart_with_buffer_size(self, buffer_size: int):
        """Shut down and restart with a new buffer size, keeping the current output device."""
        self._buffer_size = buffer_size
        self.restart_with_device(self._output_device_index)

    def restart_with_backend(self, audio_backend: str):
        """Shut down and restart with a new audio backend, keeping the current output device."""
        self._audio_backend = audio_backend
        self.restart_with_device(self._output_device_index)

    # ── Note events ───────────────────────────────────────────────

    def note_on(self, note: int, velocity: int = 127):
        self.held_notes.add(note)
        self._cmd_queue.put({'type': 'note_on', 'note': note, 'velocity': velocity})

    def note_off(self, note: int, velocity: int = 0):
        self.held_notes.discard(note)
        self._cmd_queue.put({'type': 'note_off', 'note': note, 'velocity': velocity})

    def all_notes_off(self):
        self.held_notes.clear()
        self._cmd_queue.put({'type': 'all_notes_off'})

    def soft_all_notes_off(self):
        self._cmd_queue.put({'type': 'soft_all_notes_off'})

    # ── Parameter updates ─────────────────────────────────────────

    def update_parameters(self, **kwargs):
        """Forward parameter changes and update local shadow for get_current_params()."""
        self._shadow_params.update(kwargs)
        self._cmd_queue.put({'type': 'param_update', 'params': kwargs})

    def get_current_params(self) -> dict:
        """Return the last-known parameter state from the local shadow copy."""
        return dict(self._shadow_params)

    def get_level_l(self) -> float:
        """Get left channel audio level (max amplitude 0.0-1.0) written by audio subprocess."""
        try:
            return struct.unpack_from('ff', self._level_shm.buf, 0)[0]
        except Exception:
            return 0.0

    def get_level_r(self) -> float:
        """Get right channel audio level (max amplitude 0.0-1.0) written by audio subprocess."""
        try:
            return struct.unpack_from('ff', self._level_shm.buf, 0)[1]
        except Exception:
            return 0.0

    def get_waveform_frame(self):
        """Return (write_pos, waveform_bytes) snapshot for copying into the visualizer shm.

        write_pos is the circular buffer's next-write index (0-2047).
        waveform_bytes is the raw 2048 x float32 buffer (8192 bytes).
        """
        _WAVEFORM_SAMPLES = 2048
        try:
            write_pos = struct.unpack_from('i', self._level_shm.buf, 8)[0]
            waveform_bytes = bytes(self._level_shm.buf[12:12 + _WAVEFORM_SAMPLES * 4])
            return write_pos, waveform_bytes
        except Exception:
            return 0, b'\x00' * (_WAVEFORM_SAMPLES * 4)

    # ── MIDI expression ───────────────────────────────────────────

    def pitch_bend_change(self, value: int):
        self._cmd_queue.put({'type': 'pitch_bend', 'value': value})

    def modulation_change(self, value: int):
        self._cmd_queue.put({'type': 'modulation', 'value': value})

    # ── Tambor drum trigger ───────────────────────────────────────

    def drum_trigger(self, note: int, velocity: int, params: dict):
        self._cmd_queue.put({
            'type': 'drum_trigger',
            'note': note,
            'velocity': velocity,
            'params': params,
        })

    def play_metronome_click(self, accent: bool = False):
        """Trigger a pre-generated click sound through the engine's audio stream.

        Uses the engine's existing audio output so no secondary stream is opened —
        required for ASIO exclusive-mode compatibility.
        """
        self._cmd_queue.put({'type': 'metronome_tick', 'accent': accent})

    def preload(self, midi_note: int, synth_params: dict):
        """Stub: preload is a drum_synth concern, not implemented on SynthEngine."""
        pass
