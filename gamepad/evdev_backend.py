# ABOUTME: evdev-based gamepad backend for Linux ARM (Raspberry Pi / OStra).
# ABOUTME: Reads EV_KEY and EV_ABS events from /dev/input and maps to GP actions.

import fcntl
import os
import sys
import time
from typing import Optional

from gamepad.actions import GP
from gamepad.button_maps import (
    EVDEV_KEY_MAP,
    EVDEV_ABS_AXIS_MAP,
    EVDEV_HAT0X,
    EVDEV_HAT0Y,
    EVDEV_TRIGGER_ABS,
)

try:
    import evdev
    from evdev import ecodes
    _EVDEV_AVAILABLE = True
except ImportError:
    _EVDEV_AVAILABLE = False


def _find_gamepad() -> Optional["evdev.InputDevice"]:
    """Return the first /dev/input device that has gamepad button capabilities."""
    if not _EVDEV_AVAILABLE:
        return None
    try:
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                keys = caps.get(ecodes.EV_KEY, [])
                # BTN_SOUTH (0x130) or BTN_GAMEPAD (0x130 alias) indicates a gamepad
                if ecodes.BTN_SOUTH in keys or ecodes.BTN_A in keys:
                    return dev
                dev.close()
            except (PermissionError, OSError):
                # Device not readable (wrong permissions or not a gamepad)
                pass
    except Exception:
        pass
    return None


class EvdevGamepadBackend:
    """Polls gamepad events via Linux evdev on ARM platforms.

    Call poll() on a regular timer (e.g. every 16ms) from the Textual asyncio
    event loop.  Uses non-blocking device.read_one() to drain events without
    blocking the event loop.

    Requires the user to be a member of the 'input' group on Linux:
        sudo usermod -aG input <username>
    """

    DEAD_ZONE = 0.15
    # Interval in seconds between keepalive writes to prevent the Xbox
    # controller firmware from timing out when xpad doesn't send GIP packets.
    _KEEPALIVE_INTERVAL = 30.0

    def __init__(self):
        self._device: Optional["evdev.InputDevice"] = None
        self._connected = False
        self._fire_callback = None             # called on button-down; set by GamepadHandler
        self._fire_button_up_callback = None   # called on button-up; set by GamepadHandler
        self._fire_axis_callback = None        # set by GamepadHandler

        # Per-axis info for normalisation (populated on connect)
        self._abs_info: dict[int, "evdev.AbsInfo"] = {}
        # Previous hat values
        self._hat0x: int = 0
        self._hat0y: int = 0
        # Previous axis values for noise suppression
        self._last_axis: dict[int, float] = {}
        # Keepalive: timestamp of last write to prevent controller power-off
        self._last_keepalive: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Find and open the first available gamepad device.

        Returns True if a device was found and opened.
        """
        if not _EVDEV_AVAILABLE:
            return False

        # Close any existing device before opening a new one to avoid leaking fds
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

        dev = _find_gamepad()
        if dev is None:
            return False

        self._device = dev
        self._connected = True

        # Set fd to non-blocking so read_one() returns None instead of blocking
        flags = fcntl.fcntl(dev.fd, fcntl.F_GETFL)
        fcntl.fcntl(dev.fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Cache absolute axis info for normalisation
        caps = dev.capabilities(absinfo=True)
        abs_caps = caps.get(ecodes.EV_ABS, [])
        for code, absinfo in abs_caps:
            self._abs_info[code] = absinfo

        return True

    def disconnect(self):
        """Close the evdev device."""
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Polling — called from the Textual asyncio timer
    # ------------------------------------------------------------------

    def poll(self):
        """Read all pending events from the evdev device (non-blocking).

        Uses read_one() to drain available events without blocking the asyncio
        event loop. The fd is set to O_NONBLOCK on connect so read_one()
        returns None immediately when no events are pending.
        """
        if not self._connected or self._device is None:
            return

        try:
            while True:
                event = self._device.read_one()
                if event is None:
                    break
                self._handle_event(event)
        except BlockingIOError:
            # No events available - normal when fd is O_NONBLOCK
            pass
        except OSError:
            # Device physically disconnected
            self._connected = False
        except Exception as exc:
            print(f"[gamepad] evdev poll error: {exc}", file=sys.stderr)

        # Periodic keepalive: write a SYN_REPORT to the device so the xpad
        # driver keeps sending GIP heartbeats to the Xbox controller firmware.
        # Without this, the Elite 2 times out and disconnects after ~5 minutes.
        now = time.monotonic()
        if now - self._last_keepalive >= self._KEEPALIVE_INTERVAL:
            self._last_keepalive = now
            try:
                self._device.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _handle_event(self, event):
        if event.type == ecodes.EV_KEY:
            action = EVDEV_KEY_MAP.get(event.code)
            if action:
                if event.value == 1:  # key-down
                    if self._fire_callback:
                        self._fire_callback(action)
                elif event.value == 0:  # key-up
                    if self._fire_button_up_callback:
                        self._fire_button_up_callback(action)

        elif event.type == ecodes.EV_ABS:
            self._handle_abs(event.code, event.value)

    def _handle_abs(self, code: int, raw_value: int):
        """Handle EV_ABS events: D-pad hats and analogue axes/triggers."""

        # D-pad hat axes — map to discrete dpad actions
        if code == EVDEV_HAT0X:
            if raw_value > 0 and self._hat0x <= 0:
                if self._fire_callback:
                    self._fire_callback(GP.DPAD_RIGHT)
            elif raw_value < 0 and self._hat0x >= 0:
                if self._fire_callback:
                    self._fire_callback(GP.DPAD_LEFT)
            elif raw_value == 0:
                # Released: fire button-up for whichever direction was held
                prev_action = GP.DPAD_RIGHT if self._hat0x > 0 else GP.DPAD_LEFT
                if self._fire_button_up_callback:
                    self._fire_button_up_callback(prev_action)
            self._hat0x = raw_value
            return

        if code == EVDEV_HAT0Y:
            # In evdev, hat Y -1 = up (y axis inverted)
            if raw_value < 0 and self._hat0y >= 0:
                if self._fire_callback:
                    self._fire_callback(GP.DPAD_UP)
            elif raw_value > 0 and self._hat0y <= 0:
                if self._fire_callback:
                    self._fire_callback(GP.DPAD_DOWN)
            elif raw_value == 0:
                # Released: fire button-up for whichever direction was held
                prev_action = GP.DPAD_UP if self._hat0y < 0 else GP.DPAD_DOWN
                if self._fire_button_up_callback:
                    self._fire_button_up_callback(prev_action)
            self._hat0y = raw_value
            return

        # Analogue axes and triggers
        action = EVDEV_ABS_AXIS_MAP.get(code)
        if action is None:
            return

        info = self._abs_info.get(code)
        if info is None:
            return

        # Normalise raw integer to float range
        if code in EVDEV_TRIGGER_ABS:
            # Triggers: 0.0 (released) to 1.0 (fully pressed)
            r = info.max - info.min
            if r == 0:
                return
            value = (raw_value - info.min) / r
        else:
            # Sticks: -1.0 to +1.0
            mid = (info.min + info.max) / 2.0
            half = (info.max - info.min) / 2.0
            if half == 0:
                return
            value = (raw_value - mid) / half

        self._dispatch_axis(action, value)

    def _dispatch_axis(self, action: str, value: float):
        """Apply dead zone and fire axis callback if value changed."""
        if abs(value) < self.DEAD_ZONE:
            value = 0.0
        prev = self._last_axis.get(action, 0.0)
        if abs(value - prev) < 0.01:
            return
        self._last_axis[action] = value
        if self._fire_axis_callback:
            self._fire_axis_callback(action, value)
