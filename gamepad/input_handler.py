# ABOUTME: Unified GamepadHandler — platform-aware gamepad input for Acordes.
# ABOUTME: Uses pygame.controller on desktop, evdev on Linux ARM.

import platform
import sys
import time
from typing import Callable, Optional

from gamepad.actions import GP


# D-pad auto-repeat timing
_REPEAT_DELAY    = 0.40   # seconds before first repeat fires
_REPEAT_INTERVAL = 0.10   # seconds between subsequent repeats

# How often poll() retries connecting when no controller is detected.
# Handles boot-time xpad initialization delays and physical reconnects.
_RECONNECT_INTERVAL = 3.0

_DPAD_ACTIONS = {GP.DPAD_UP, GP.DPAD_DOWN, GP.DPAD_LEFT, GP.DPAD_RIGHT}


class GamepadHandler:
    """Cross-platform gamepad input handler for Acordes.

    Instantiate once in AcordesApp.__init__() and add to app_context.
    Call poll() on a Textual set_interval timer (e.g. every 0.016s) from
    MainScreen.on_mount().  All callbacks fire on the asyncio event loop
    thread (the same thread that calls poll()), so no cross-thread locking
    is needed.

    Callback registration is split into two tiers:
      - Global callbacks (set_global_button_callback): persist across mode
        switches; used for Start (main menu), Back (history), LB+RB (panic).
      - Per-mode callbacks (set_button_callback / set_axis_callback): cleared
        by clear_callbacks() which each mode calls in on_mode_pause().

    Combo detection:
      Use set_combo_callback() to register a callback that fires when all
      listed GP.* actions are held simultaneously.  Combos are checked before
      individual button callbacks and suppress the individual firing.
    """

    def __init__(self):
        self._backend = None
        self._connected = False

        # Global callbacks — never cleared by clear_callbacks()
        self._global_button_cbs:  dict[str, Callable] = {}
        self._global_axis_cbs:    dict[str, Callable] = {}
        self._global_combo_cbs:   dict[frozenset, Callable] = {}

        # Per-mode callbacks — cleared on mode switch
        self._button_cbs:  dict[str, Callable] = {}
        self._axis_cbs:    dict[str, Callable] = {}
        self._combo_cbs:   dict[frozenset, Callable] = {}

        # Held-button tracking for combo detection
        self._held: set[str] = set()

        # Optional activity callback called on every button-down or axis event.
        # Set by MainScreen to reset the idle/screensaver timer on any input.
        self._activity_callback: Optional[Callable] = None

        # D-pad auto-repeat state
        self._repeat_action: Optional[str] = None
        self._repeat_next:   float = 0.0
        self._repeat_phase:  str = "idle"   # "idle" | "delay" | "repeat"

        # Auto-reconnect: next time poll() may attempt a reconnect
        self._next_reconnect: float = 0.0

        # Select platform backend
        self._backend = self._create_backend()
        if self._backend is not None:
            self._backend._fire_callback = self._on_button_down
            self._backend._fire_button_up_callback = self._on_button_up
            self._backend._fire_axis_callback = self._on_axis

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------

    @staticmethod
    def _create_backend():
        """Return the appropriate backend for the current platform."""
        machine = platform.machine()
        is_arm_linux = sys.platform == "linux" and machine in ("armv7l", "aarch64")

        if is_arm_linux:
            try:
                from gamepad.evdev_backend import EvdevGamepadBackend
                return EvdevGamepadBackend()
            except Exception as exc:
                print(f"[gamepad] evdev backend unavailable: {exc}", file=sys.stderr)
        elif sys.platform == "win32":
            try:
                from gamepad.xinput_backend import XInputGamepadBackend
                return XInputGamepadBackend()
            except Exception as exc:
                print(f"[gamepad] XInput backend unavailable: {exc}", file=sys.stderr)
        else:
            try:
                from gamepad.pygame_backend import PygameGamepadBackend
                return PygameGamepadBackend()
            except Exception as exc:
                print(f"[gamepad] pygame backend unavailable: {exc}", file=sys.stderr)

        return None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Try to open the first available gamepad.  Returns True on success."""
        if self._backend is None:
            return False
        result = self._backend.connect()
        self._connected = result
        if result:
            print("[gamepad] controller connected", file=sys.stderr)
        return result

    def reconnect(self) -> bool:
        """Disconnect and reconnect to get a fresh device fd.

        Called after a short delay on ARM boot to work around xpad driver
        initialization timing: the kernel registers the event device before
        the driver finishes its USB handshake, so the first connect() gets
        a stale fd that receives no events.  Reopening after a few seconds
        picks up the fully-initialized stream.
        """
        self.disconnect()
        result = self.connect()
        if not result:
            print("[gamepad] reconnect failed — no controller found", file=sys.stderr)
        return result

    def disconnect(self):
        """Close the gamepad device."""
        if self._backend is not None:
            self._backend.disconnect()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected and (
            self._backend is not None and self._backend.is_connected()
        )

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def set_global_button_callback(self, action: str, callback: Callable):
        """Register a button callback that persists across mode switches."""
        self._global_button_cbs[action] = callback

    def set_global_axis_callback(self, action: str, callback: Callable[[float], None]):
        """Register an axis callback that persists across mode switches."""
        self._global_axis_cbs[action] = callback

    def set_global_combo_callback(self, actions: tuple, callback: Callable):
        """Register a combo callback that persists across mode switches."""
        self._global_combo_cbs[frozenset(actions)] = callback

    def set_button_callback(self, action: str, callback: Callable):
        """Register a per-mode button callback (cleared on mode pause)."""
        self._button_cbs[action] = callback

    def set_axis_callback(self, action: str, callback: Callable[[float], None]):
        """Register a per-mode axis callback (cleared on mode pause)."""
        self._axis_cbs[action] = callback

    def set_combo_callback(self, actions: tuple, callback: Callable):
        """Register a per-mode combo callback (cleared on mode pause)."""
        self._combo_cbs[frozenset(actions)] = callback

    def get_button_callback(self, action: str):
        """Return the current per-mode button callback for an action, or None."""
        return self._button_cbs.get(action)

    def clear_callbacks(self):
        """Clear all per-mode callbacks.  Call this in on_mode_pause()."""
        self._button_cbs.clear()
        self._axis_cbs.clear()
        self._combo_cbs.clear()

    # ------------------------------------------------------------------
    # Polling — called from Textual set_interval timer
    # ------------------------------------------------------------------

    def poll(self):
        """Poll the backend and process D-pad auto-repeat.

        Must be called regularly from the Textual asyncio event loop, e.g.
        via set_interval(0.016, gamepad_handler.poll) in MainScreen.on_mount().
        Exceptions from the backend or callbacks are caught here so a single
        bad event can never crash the Textual event loop.

        When not connected, retries connect() every _RECONNECT_INTERVAL seconds.
        This handles both boot-time xpad initialization delays (the kernel
        registers the event device before the driver finishes its USB handshake)
        and physical controller reconnects during a session.
        """
        if not self.is_connected():
            now = time.monotonic()
            if now >= self._next_reconnect:
                self._next_reconnect = now + _RECONNECT_INTERVAL
                self.connect()
            return

        try:
            self._backend.poll()
        except Exception as exc:
            print(f"[gamepad] backend poll error: {exc}", file=sys.stderr)

        self._process_dpad_repeat()

    # ------------------------------------------------------------------
    # Event dispatch (called by backend on each button/axis event)
    # ------------------------------------------------------------------

    def _on_button_down(self, action: str):
        """Handle a button-down event from the backend."""
        if self._activity_callback:
            self._safe_call(self._activity_callback)
        self._held.add(action)

        # Check global combos first — sort by size descending so more specific
        # combos (e.g. LB+RB+Start) take priority over subsets (e.g. LB+RB).
        for combo, cb in sorted(self._global_combo_cbs.items(), key=lambda x: len(x[0]), reverse=True):
            if combo.issubset(self._held):
                self._safe_call(cb)
                return

        # Check per-mode combos (also most-specific first)
        for combo, cb in sorted(self._combo_cbs.items(), key=lambda x: len(x[0]), reverse=True):
            if combo.issubset(self._held):
                self._safe_call(cb)
                return

        # D-pad: fire immediately and start auto-repeat
        if action in _DPAD_ACTIONS:
            self._fire_button(action)
            self._start_dpad_repeat(action)
            return

        # Regular button
        self._fire_button(action)

    def _on_button_up(self, action: str):
        """Handle a button-up event from the backend.

        Removes the action from the held-button set so combos and D-pad
        auto-repeat stop correctly when the button is released.
        """
        self._held.discard(action)
        # Stop D-pad auto-repeat when the direction is released
        if action == self._repeat_action:
            self._repeat_action = None
            self._repeat_phase = "idle"

    def _fire_button(self, action: str):
        """Fire the callback registered for action (per-mode then global)."""
        cb = self._button_cbs.get(action) or self._global_button_cbs.get(action)
        if cb:
            self._safe_call(cb)

    def _on_axis(self, action: str, value: float):
        """Handle an axis value change from the backend."""
        if self._activity_callback:
            self._safe_call(self._activity_callback)
        cb = self._axis_cbs.get(action) or self._global_axis_cbs.get(action)
        if cb:
            self._safe_call(cb, value)

    def _safe_call(self, cb, *args):
        """Call cb(*args), printing any exception to stderr without propagating.

        Prevents a misbehaving mode callback from crashing the poll timer and
        taking down the Textual event loop (which would crash Windows Terminal).
        """
        try:
            cb(*args)
        except Exception as exc:
            print(f"[gamepad] callback error: {exc}", file=sys.stderr)

    # ------------------------------------------------------------------
    # D-pad auto-repeat
    # ------------------------------------------------------------------

    def _start_dpad_repeat(self, action: str):
        """Begin auto-repeat for a D-pad direction."""
        self._repeat_action = action
        self._repeat_next = time.monotonic() + _REPEAT_DELAY
        self._repeat_phase = "delay"

    def _process_dpad_repeat(self):
        """Fire repeat events for a held D-pad direction."""
        if self._repeat_phase == "idle" or self._repeat_action is None:
            return

        # Stop repeat if the button is no longer held
        if self._repeat_action not in self._held:
            self._repeat_action = None
            self._repeat_phase = "idle"
            return

        now = time.monotonic()
        if now < self._repeat_next:
            return

        # Fire repeat (only if button still held according to backend state)
        self._fire_button(self._repeat_action)
        self._repeat_next = now + _REPEAT_INTERVAL
        self._repeat_phase = "repeat"

