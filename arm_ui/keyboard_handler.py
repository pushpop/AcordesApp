# ABOUTME: Reads keyboard input via evdev on ARM and posts pygame KEYDOWN events.
# ABOUTME: Bridges the gap when SDL_VIDEODRIVER=dummy cannot receive OS keyboard events.

import sys
import threading

import pygame

# evdev key code -> pygame key constant
# Only maps keys used for navigation in the ARM UI.
_EVDEV_TO_PYGAME = {
    1:   pygame.K_ESCAPE,      # KEY_ESC
    14:  pygame.K_BACKSPACE,   # KEY_BACKSPACE
    28:  pygame.K_RETURN,      # KEY_ENTER
    57:  pygame.K_SPACE,       # KEY_SPACE
    96:  pygame.K_RETURN,      # KEY_KPENTER
    103: pygame.K_UP,          # KEY_UP
    105: pygame.K_LEFT,        # KEY_LEFT
    106: pygame.K_RIGHT,       # KEY_RIGHT
    108: pygame.K_DOWN,        # KEY_DOWN
    # Letter shortcuts
    30:  pygame.K_a,           # KEY_A
    32:  pygame.K_d,           # KEY_D
    19:  pygame.K_r,           # KEY_R
    31:  pygame.K_s,           # KEY_S
    48:  pygame.K_b,           # KEY_B
    51:  pygame.K_COMMA,       # KEY_COMMA
    52:  pygame.K_PERIOD,      # KEY_DOT
}


def _find_keyboard():
    """Return the first evdev device that looks like a keyboard, or None."""
    try:
        import evdev
        from evdev import ecodes
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                keys = caps.get(ecodes.EV_KEY, [])
                # A real keyboard has letter keys (KEY_A=30) and arrow keys
                if ecodes.KEY_A in keys and ecodes.KEY_LEFT in keys:
                    return dev
            except Exception:
                continue
    except Exception:
        pass
    return None


class KeyboardHandler:
    """Polls an evdev keyboard device in a background thread.

    Key-down events are translated to pygame.KEYDOWN events and posted to
    pygame's event queue, which the main loop drains via pygame.event.get().
    Works transparently with SDL_VIDEODRIVER=dummy since pygame.event.post()
    bypasses the display driver entirely.

    Silently does nothing if evdev is unavailable (Windows dev machine) or
    no keyboard device is found.
    """

    def __init__(self) -> None:
        self._device = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Find keyboard device and start background polling thread."""
        device = _find_keyboard()
        if device is None:
            print("[keyboard_handler] no keyboard device found; skipping.", file=sys.stderr)
            return
        self._device  = device
        self._running = True
        self._thread  = threading.Thread(
            target=self._poll, daemon=True, name="arm-keyboard"
        )
        self._thread.start()
        print(f"[keyboard_handler] reading {device.name} ({device.path})", file=sys.stderr)

    def stop(self) -> None:
        """Stop the polling thread."""
        self._running = False
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass

    def _poll(self) -> None:
        """Background thread: translate evdev key events to pygame events."""
        try:
            import evdev
            from evdev import ecodes
            for event in self._device.read_loop():
                if not self._running:
                    break
                if event.type != ecodes.EV_KEY:
                    continue
                key_event = evdev.categorize(event)
                # key_down = 1, key_hold = 2 - handle both for held keys
                if key_event.keystate not in (
                    evdev.events.KeyEvent.key_down,
                    evdev.events.KeyEvent.key_hold,
                ):
                    continue
                pygame_key = _EVDEV_TO_PYGAME.get(event.code)
                if pygame_key is None:
                    continue
                try:
                    pygame.event.post(
                        pygame.event.Event(
                            pygame.KEYDOWN,
                            key=pygame_key,
                            mod=0,
                            unicode="",
                        )
                    )
                except Exception:
                    pass
        except Exception as exc:
            if self._running:
                print(f"[keyboard_handler] poll error: {exc}", file=sys.stderr)
