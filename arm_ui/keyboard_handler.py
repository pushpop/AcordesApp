# ABOUTME: Reads keyboard input via evdev on ARM and posts pygame KEYDOWN events.
# ABOUTME: Non-blocking poll() called from the main loop - no background thread.

import os
import sys

import pygame

try:
    import fcntl
    import evdev
    from evdev import ecodes
    _EVDEV_AVAILABLE = True
except ImportError:
    _EVDEV_AVAILABLE = False

# evdev key code -> pygame key constant.
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
    30:  pygame.K_a,           # KEY_A
    32:  pygame.K_d,           # KEY_D
    19:  pygame.K_r,           # KEY_R
    31:  pygame.K_s,           # KEY_S
    48:  pygame.K_b,           # KEY_B
    51:  pygame.K_COMMA,       # KEY_COMMA
    52:  pygame.K_PERIOD,      # KEY_DOT
}


def _find_keyboard():
    """Return the first evdev device that looks like a keyboard, or None.

    Requires EV_KEY capability with both KEY_A and KEY_LEFT to distinguish
    a real keyboard from gamepads, touchscreens, and power buttons.
    """
    if not _EVDEV_AVAILABLE:
        return None
    try:
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                keys = caps.get(ecodes.EV_KEY, [])
                if ecodes.KEY_A in keys and ecodes.KEY_LEFT in keys:
                    return dev
                dev.close()
            except (PermissionError, OSError):
                pass
    except Exception:
        pass
    return None


class KeyboardHandler:
    """Non-blocking keyboard poller using evdev.

    poll() is called from the main loop (no background thread). It drains
    all pending key events using O_NONBLOCK read_one(), translates them to
    pygame.KEYDOWN events, and posts them via pygame.event.post().

    pygame.event.post() bypasses the SDL display driver so it works with
    SDL_VIDEODRIVER=dummy. The events appear in the normal pygame.event.get()
    queue consumed by handle_event() in each screen.

    Silently does nothing on Windows / if evdev is unavailable / if no
    keyboard device is found.
    """

    def __init__(self) -> None:
        self._device = None

    def start(self) -> None:
        """Find keyboard device and set it to non-blocking mode."""
        device = _find_keyboard()
        if device is None:
            print("[keyboard_handler] no keyboard found; skipping.", file=sys.stderr)
            return
        # Set O_NONBLOCK so read_one() returns None immediately when empty,
        # matching the same pattern used by EvdevGamepadBackend.
        fl = fcntl.fcntl(device.fd, fcntl.F_GETFL)  # type: ignore[name-defined]
        fcntl.fcntl(device.fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)  # type: ignore[name-defined]
        self._device = device
        print(f"[keyboard_handler] {device.name} ({device.path})", file=sys.stderr)

    def stop(self) -> None:
        """Close the keyboard device."""
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    def poll(self) -> None:
        """Drain all pending key events and post pygame KEYDOWN events.

        Non-blocking: returns immediately when no events are pending.
        Call this from the main loop alongside gamepad_handler.poll().
        """
        if self._device is None:
            return
        try:
            while True:
                event = self._device.read_one()
                if event is None:
                    break
                if event.type != ecodes.EV_KEY:
                    continue
                # key_down=1 only; skip key_up=0 and key_hold=2
                if event.value != 1:
                    continue
                pygame_key = _EVDEV_TO_PYGAME.get(event.code)
                if pygame_key is None:
                    continue
                try:
                    pygame.event.post(
                        pygame.event.Event(
                            pygame.KEYDOWN, key=pygame_key, mod=0, unicode=""
                        )
                    )
                except Exception:
                    pass
        except BlockingIOError:
            pass  # No events pending - normal with O_NONBLOCK
        except OSError:
            self._device = None
        except Exception as exc:
            print(f"[keyboard_handler] poll error: {exc}", file=sys.stderr)
