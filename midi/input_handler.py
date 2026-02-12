"""Real-time MIDI input processing."""
import mido
from typing import Set, Optional, Callable
from threading import Lock


class MIDIInputHandler:
    """Handles MIDI input reading and note tracking."""

    def __init__(self):
        self.port: Optional[mido.ports.BaseInput] = None
        self.active_notes: Set[int] = set()
        self.notes_lock = Lock()
        self._note_on_callback: Optional[Callable[[int], None]] = None
        self._note_off_callback: Optional[Callable[[int], None]] = None

    def open_device(self, device_name: str) -> bool:
        """Open a MIDI input device.

        Args:
            device_name: Name of the MIDI device to open.

        Returns:
            True if device opened successfully, False otherwise.
        """
        try:
            self.close_device()
            self.port = mido.open_input(device_name)
            return True
        except Exception as e:
            print(f"Error opening MIDI device: {e}")
            return False

    def close_device(self):
        """Close the current MIDI input device."""
        if self.port:
            try:
                self.port.close()
            except Exception as e:
                print(f"Error closing MIDI device: {e}")
            finally:
                self.port = None

        with self.notes_lock:
            self.active_notes.clear()

    def set_callbacks(self, note_on: Callable[[int], None],
                     note_off: Callable[[int], None]):
        """Set callbacks for note events.

        Args:
            note_on: Callback function called when a note is pressed.
            note_off: Callback function called when a note is released.
        """
        self._note_on_callback = note_on
        self._note_off_callback = note_off

    def poll_messages(self):
        """Poll for pending MIDI messages (non-blocking).

        Should be called regularly to process incoming MIDI data.
        """
        if not self.port:
            return

        try:
            for msg in self.port.iter_pending():
                if msg.type == 'note_on' and msg.velocity > 0:
                    self._handle_note_on(msg.note)
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    self._handle_note_off(msg.note)
        except Exception as e:
            print(f"Error polling MIDI messages: {e}")

    def _handle_note_on(self, note: int):
        """Handle NOTE_ON message."""
        with self.notes_lock:
            self.active_notes.add(note)

        if self._note_on_callback:
            self._note_on_callback(note)

    def _handle_note_off(self, note: int):
        """Handle NOTE_OFF message."""
        with self.notes_lock:
            self.active_notes.discard(note)

        if self._note_off_callback:
            self._note_off_callback(note)

    def get_active_notes(self) -> Set[int]:
        """Get set of currently pressed notes.

        Returns:
            Set of MIDI note numbers currently pressed.
        """
        with self.notes_lock:
            return self.active_notes.copy()

    def is_device_open(self) -> bool:
        """Check if a MIDI device is currently open.

        Returns:
            True if a device is open.
        """
        return self.port is not None
