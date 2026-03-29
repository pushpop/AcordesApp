#!/usr/bin/env python3
"""MIDI Piano TUI Application - Main Entry Point."""
import multiprocessing
import os
import sys

# Workaround for a Python 3.11 ARM bug: the multiprocessing resource tracker
# (spawned lazily by numpy/OpenBLAS semaphore creation) can receive fd -1 in
# its passfds set, causing "ValueError: bad value(s) in fds_to_keep".
# Filter out any negative fds before the C-level fork_exec call.
import multiprocessing.util as _mp_util
def _safe_spawnv_passfds(path, args, passfds, _orig=_mp_util.spawnv_passfds):
    # Original captured as default arg so it survives module-level cleanup.
    passfds = tuple(fd for fd in passfds if fd >= 0)
    return _orig(path, args, passfds)
_mp_util.spawnv_passfds = _safe_spawnv_passfds
del _mp_util, _safe_spawnv_passfds

# Suppress the Pygame "hello" message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"

# ARM real-time audio: tighten the GIL switch interval from the default 5ms
# to 1ms.  The PortAudio callback runs in a C thread; when the Textual UI
# thread holds the GIL for a full 5ms slice during widget rendering, the
# callback thread waits and misses its deadline, producing output_underflow
# xruns even at low CPU utilisation.  At 1ms the audio thread gets the GIL
# much more frequently, keeping callbacks on time without a busy-wait loop.
import platform as _platform
if _platform.machine() in ("armv7l", "aarch64"):
    sys.setswitchinterval(0.001)
    # uvloop replaces the default asyncio event loop with a libuv-based
    # implementation that is 2-4x faster at event dispatch on Linux/ARM.
    # This reduces the latency between a keypress and the resulting render,
    # improving navigation responsiveness across all modes.
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
del _platform

# Note: On Windows, mido will auto-detect available MIDI backends
# We don't force a specific backend to avoid DLL issues

import glob
import platform
import subprocess
import time
from typing import Optional

from textual.app import App
from textual.binding import Binding
from textual.widgets import Static, Header, Footer
from textual.containers import Vertical, Container
from textual.screen import Screen

from config_manager import ConfigManager
from midi.device_manager import MIDIDeviceManager
from midi.input_handler import MIDIInputHandler
from music.chord_detector import ChordDetector
from music.chord_library import ChordLibrary
from music.engine_proxy import SynthEngineProxy
from music.synth_engine import list_output_devices

from modes.config_mode import ConfigMode
from modes.piano_mode import PianoMode
from modes.compendium_mode import CompendiumMode
from modes.synth_mode import SynthMode
from modes.metronome_mode import MetronomeMode
from modes.main_menu_mode import MainMenuMode
from modes.tambor.tambor_mode import TamborMode
from components.confirmation_dialog import ConfirmationDialog
from gamepad import GamepadHandler, GP


class LoadingScreen(Screen):
    """ABOUTME: Startup loading screen shown while the audio engine process initialises.
    ABOUTME: Polls the proxy ready event and transitions to the main screen when ready."""

    _SPINNER = "|/-\\"

    CSS = """
    LoadingScreen {
        align: center middle;
        background: $background;
    }
    #loading-box {
        width: 52;
        height: auto;
        border: solid $accent;
        padding: 1 2;
        align: center middle;
    }
    #loading-title {
        text-align: center;
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    #loading-spinner {
        text-align: center;
        color: $text;
    }
    #loading-info {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(self, proxy: SynthEngineProxy, on_ready_callback):
        super().__init__()
        self._proxy = proxy
        self._on_ready_callback = on_ready_callback
        self._poll_timer = None
        self._spin_timer = None
        self._spin_idx = 0
        self._done = False

    def compose(self):
        from textual.containers import Vertical
        from textual.widgets import Static
        with Vertical(id="loading-box"):
            yield Static("A C O R D E S", id="loading-title")
            yield Static("|  Starting audio engine...", id="loading-spinner")
            yield Static("", id="loading-info")

    def on_mount(self):
        self._poll_timer = self.set_interval(0.1, self._check_ready)
        self._spin_timer = self.set_interval(0.1, self._tick_spinner)

    def _tick_spinner(self):
        if self._done:
            return
        char = self._SPINNER[self._spin_idx % len(self._SPINNER)]
        self._spin_idx += 1
        self.query_one("#loading-spinner").update(f"{char}  Starting audio engine...")

    def _check_ready(self):
        err = self._proxy.get_error()
        if err:
            self._done = True
            self.query_one("#loading-spinner").update(f"[red]Audio error: {err}[/]")
            if self._poll_timer:
                self._poll_timer.stop()
            if self._spin_timer:
                self._spin_timer.stop()
            return

        if self._proxy.is_available():
            self._done = True
            if self._poll_timer:
                self._poll_timer.stop()
            if self._spin_timer:
                self._spin_timer.stop()

            self.query_one("#loading-spinner").update("[#d79b00]ready[/]")

            # Show engine diagnostics if the subprocess populated them (ARM only).
            info = self._proxy.get_startup_info()
            if info:
                self.query_one("#loading-info").update(info)

            # Brief pause so the user can read the info before transitioning.
            self.set_timer(1.2 if info else 0.3, self._on_ready_callback)


class SynthHelpBar(Static):
    """ABOUTME: Help bar displaying Synth keybinds - shown only in Synth mode.
    ABOUTME: Displays keyboard shortcuts for Synth operations on two lines."""

    def render(self) -> str:
        """Render the help bar with two lines of keybinds."""
        line1 = "WASD: Navigate | Q/E: Adjust | _: Randomize | R: Reset | I: Init | ENTER: Focus"
        line2 = ",/.: Presets | \\[/]: Volume | Ctrl+N: Save | Ctrl+S: Update | SPACE: Panic | -: Random All"
        return f"{line1}\n{line2}"


class TamborHelpBar(Static):
    """ABOUTME: Help bar displaying Tambor keybinds - shown only in Tambor mode.
    ABOUTME: Displays keyboard shortcuts for all Tambor operations on two lines."""

    def render(self) -> str:
        """Render the help bar with two lines of keybinds."""
        line1 = "↑↓: Drums | ←→: Steps/M-S | SPACE: Play/Stop | ENTER: Toggle | E: Edit | M: Mute | S: Solo | H: Humanize"
        line2 = "R: Random | F: Fill | C: Clear | T: PRE-SCALE | N: Pattern | +/-: Steps"
        return f"{line1}\n{line2}"


class MetronomeHelpBar(Static):
    """ABOUTME: Help bar displaying Metronome keybinds - shown only in Metronome mode.
    ABOUTME: Displays keyboard shortcuts for metronome control on two lines."""

    def render(self) -> str:
        """Render the help bar with two lines of keybinds."""
        line1 = "P / SPACE: Start/Stop | ↑: Tempo + | ↓: Tempo - | ←: Time Sig - | →: Time Sig +"
        line2 = ""
        return line1 if not line2 else f"{line1}\n{line2}"


class CompendiumHelpBar(Static):
    """ABOUTME: Help bar displaying Compendium keybinds - shown only in Compendium mode.
    ABOUTME: Displays keyboard shortcuts for chord library browsing."""

    def render(self) -> str:
        """Render the help bar with two lines of keybinds."""
        line1 = "SPACE: Play Chord | E: Expand All | ↑↓←→: Navigate"
        line2 = "TAB: Search"
        return line1 if not line2 else f"{line1}\n{line2}"


class IdleManager:
    """ABOUTME: Tracks user inactivity and blanks screen + lowers CPU when idle.
    ABOUTME: ARM-only screen blank via /dev/fb0; CPU governor via cpufreq sysfs."""

    # Default idle timeout in seconds before screen blanks.
    DEFAULT_TIMEOUT = 300  # 5 minutes

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self._timeout = timeout
        self._last_activity = time.monotonic()
        self._is_idle = False
        self._is_arm = platform.machine() in ("armv7l", "aarch64")
        # Optional callback invoked on the event-loop thread when waking from
        # idle.  Set by MainScreen to force a Textual repaint after the display
        # was blanked by writing directly to /dev/fb0.
        self._on_wake = None

    @property
    def is_idle(self) -> bool:
        """Return True if the screen is currently in idle/blanked state."""
        return self._is_idle

    def reset(self):
        """Record user activity and wake up from idle if currently idle."""
        self._last_activity = time.monotonic()
        if self._is_idle:
            self._exit_idle()

    def check(self):
        """Check whether the idle threshold has been crossed; call periodically."""
        if self._is_idle:
            return
        elapsed = time.monotonic() - self._last_activity
        if elapsed >= self._timeout:
            self._enter_idle()

    def _enter_idle(self):
        """Blank the screen and lower CPU governor."""
        self._is_idle = True
        self._blank_display()
        self._set_governor("powersave")

    def _exit_idle(self):
        """Restore display and raise CPU governor."""
        self._is_idle = False
        self._set_governor("performance")
        # Force a full Textual repaint so the UI overwrites the blanked /dev/fb0.
        if self._on_wake is not None:
            self._on_wake()

    def _blank_display(self):
        """Write a dark grey frame to /dev/fb0 for the screensaver (ARM only).

        Uses dark grey (RGB 40, 40, 40) instead of pure black so the display
        shows a visible screensaver rather than appearing completely dead.
        Supports 32bpp (BGRA/XRGB) and 16bpp (RGB565) framebuffer formats.
        """
        if not self._is_arm:
            return
        try:
            fb_path = "/dev/fb0"
            with open("/sys/class/graphics/fb0/virtual_size") as f:
                w, h = map(int, f.read().strip().split(","))
            with open("/sys/class/graphics/fb0/bits_per_pixel") as f:
                bpp = int(f.read().strip())
            with open("/sys/class/graphics/fb0/stride") as f:
                stride = int(f.read().strip())
            total_bytes = stride * h
            bytes_per_pixel = max(1, bpp // 8)
            # Dark grey pixel value for each supported pixel format.
            # RGB(40, 40, 40) = 0x28 per channel.
            if bpp == 32:
                # BGRA or XRGB: four bytes per pixel, alpha = opaque.
                pixel = bytes([0x28, 0x28, 0x28, 0xff])
            elif bpp == 16:
                # RGB565: R=5, G=10, B=5 → 0x2945, little-endian.
                pixel = bytes([0x45, 0x29])
            else:
                pixel = b"\x00" * bytes_per_pixel
            pixel_count = total_bytes // bytes_per_pixel
            frame = pixel * pixel_count
            # Pad to exact byte count in case stride creates a fractional pixel.
            if len(frame) < total_bytes:
                frame += b"\x00" * (total_bytes - len(frame))
            with open(fb_path, "wb") as fb:
                fb.write(frame[:total_bytes])
        except Exception:
            # /dev/fb0 not available or permission denied - silently skip.
            pass

    def _set_governor(self, governor: str):
        """Write CPU governor to all cores via cpufreq sysfs (best-effort, no sudo)."""
        if not self._is_arm:
            return
        paths = glob.glob(
            "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
        )
        for path in paths:
            try:
                with open(path, "w") as f:
                    f.write(governor)
            except Exception:
                # Permission denied without root - silently skip.
                pass


class MainScreen(Screen):
    """Main screen with split layout."""

    CSS = """
    MainScreen {
        layout: vertical;
    }

    Header {
        height: auto;
        border: none;
    }

    #content-area {
        height: 1fr;
        width: 100%;
        align: center middle;
    }


    #synth-help-bar {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        padding: 0;
        margin: 0;
        border-top: solid $accent;
    }

    #tambor-help-bar {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        padding: 0;
        margin: 0;
        border-top: solid $accent;
    }

    #metronome-help-bar {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        padding: 0;
        margin: 0;
        border-top: solid $accent;
    }

    #compendium-help-bar {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        padding: 0;
        margin: 0;
        border-top: solid $accent;
    }
    """

    BINDINGS = [
        Binding("0", "show_main_menu", "Menu", show=True),
        Binding("1", "show_piano", "Piano", show=True),
        Binding("2", "show_compendium", "Compendium", show=True),
        Binding("3", "show_synth", "Synth", show=True),
        Binding("4", "show_metronome", "Metronome", show=True),
        Binding("5", "show_tambor", "Tambor", show=True),
        Binding("c", "show_config", "Config", show=True),
        Binding("backspace", "go_back", "Back", show=True),
        Binding("escape", "quit_app", "Quit", show=True),
    ]

    def action_toggle_header(self) -> None:
        """Prevent the default header toggle action."""
        pass  # Disabled - do nothing

    def __init__(self, app_context):
        super().__init__()
        self.app_context = app_context
        self.mode_history = []
        self._help_bars: dict[str, Optional[Static]] = {
            "synth": None,
            "tambor": None,
            "metronome": None,
            "compendium": None,
        }
        # Cache of mounted mode widgets, keyed by mode_name.
        # On ARM, keeping widgets mounted (display toggled) avoids the ~300ms
        # re-creation cost of Textual widget trees on every mode switch.
        self._mode_cache: dict = {}
        # Idle manager: blanks screen and lowers CPU after inactivity.
        self._idle_manager = IdleManager()
        self._idle_check_timer = None

    def compose(self):
        """Compose the main screen layout."""
        header = Header()
        header.can_focus = False
        # Prevent header from expanding when clicked
        if hasattr(header, 'expand'):
            header.expand = False
        yield header

        # Content area for Piano or Compendium - NO CONTAINER
        with Container(id="content-area"):
            pass

        # Help bar will be mounted dynamically when in Tambor mode
        # It's not yielded here because we only want it visible in Tambor mode

        yield Footer()

    def on_mount(self):
        """Called when mounted."""
        # Show initial mode
        self.action_show_main_menu(save_history=False)
        # Check for idle every 30 seconds.
        self._idle_check_timer = self.set_interval(30, self._on_idle_check)
        # Register activity hook so MIDI note-on events reset the idle timer.
        # This is independent of mode callbacks so it survives mode switches.
        midi_handler = self.app_context.get("midi_handler")
        if midi_handler is not None:
            midi_handler._activity_callback = self._idle_manager.reset
        # Wake callback: force a full Textual repaint after the screensaver
        # blanked /dev/fb0 directly.  Without this Textual's dirty-tracking
        # believes the screen is still up-to-date and emits no ANSI codes.
        self._idle_manager._on_wake = lambda: self.refresh(repaint=True)
        # Start gamepad polling and wire global bindings.
        gp = self.app_context.get("gamepad_handler")
        if gp is not None:
            # Any gamepad button or axis event resets the idle/screensaver timer.
            gp._activity_callback = self._idle_manager.reset
            self._setup_gamepad_globals(gp)
            self.set_interval(0.033, gp.poll)

    def _setup_gamepad_globals(self, gp):
        """Wire global gamepad bindings that persist across all mode switches.

        Start + Back held together opens config regardless of press order.
        Each button checks if its partner is already held; if so it routes to
        config instead of its individual action.  This avoids the double-fire
        problem that occurs when using a registered combo (the first button
        always fires its individual callback before the combo can complete).
        """
        def _gp_start():
            if GP.BACK_BTN in gp._held:
                self.action_show_config()
            else:
                self.action_show_main_menu()

        def _gp_back_btn():
            if GP.START in gp._held:
                self.action_show_config()
            else:
                self.action_go_back()

        gp.set_global_button_callback(GP.START, _gp_start)
        gp.set_global_button_callback(GP.BACK_BTN, _gp_back_btn)
        # LB + RB simultaneously = panic (all notes off)
        gp.set_global_combo_callback(
            (GP.LB, GP.RB),
            lambda: self.app_context["synth_engine"].all_notes_off()
        )

    def _on_idle_check(self):
        """Periodic callback to check idle state and blank screen if needed."""
        self._idle_manager.check()

    def on_key(self, event) -> None:
        """Reset idle timer on any keypress and stop arrow keys from escaping.

        On Windows, Xbox controller D-pad presses inject real keyboard arrow
        events into the terminal alongside the SDL gamepad events we poll.
        If those injected events bubble past all mode widgets they reach
        Windows Terminal's own UI (tab bar), which crashes the session.
        Calling event.stop() here absorbs them after all mode BINDINGS and
        on_key handlers have already had a chance to act on the event.
        """
        self._idle_manager.reset()
        if event.key in ("up", "down", "left", "right"):
            event.stop()

    def _record_history(self):
        """Record current mode to history if it's different from the last entry."""
        current = self.app_context.get("current_mode")
        if current:
            if not self.mode_history or self.mode_history[-1] != current:
                self.mode_history.append(current)

    def action_go_back(self):
        """Go back to the previous mode, or show quit dialog if already at main menu."""
        if not self.mode_history:
            if self.app_context.get("current_mode") != "main_menu":
                self.action_show_main_menu(save_history=False)
            else:
                # Already at main menu with no history: offer to quit
                self.action_quit_app()
            return

        previous_mode = self.mode_history.pop()
        
        # Dispatch to the appropriate show method without saving history again
        if previous_mode == "main_menu":
            self.action_show_main_menu(save_history=False)
        elif previous_mode == "piano":
            self.action_show_piano(save_history=False)
        elif previous_mode == "compendium":
            self.action_show_compendium(save_history=False)
        elif previous_mode == "synth":
            self.action_show_synth(save_history=False)
        elif previous_mode == "metronome":
            self.action_show_metronome(save_history=False)
        elif previous_mode == "tambor":
            self.action_show_tambor(save_history=False)

    def action_show_main_menu(self, save_history=True):
        """Show main menu mode."""
        if save_history:
            self._record_history()
        self._switch_mode(lambda: self.app_context["create_main_menu"](self), "main_menu")


    def _apply_help_bars(self, mode_name: str):
        """Mount the help bar for mode_name and remove help bars for all other modes."""
        modes_with_help = {
            "synth": SynthHelpBar,
            "tambor": TamborHelpBar,
            "metronome": MetronomeHelpBar,
            "compendium": CompendiumHelpBar,
        }

        if mode_name in modes_with_help:
            if self._help_bars[mode_name] is None:
                help_bar_class = modes_with_help[mode_name]
                self._help_bars[mode_name] = help_bar_class(id=f"{mode_name}-help-bar")
                self.mount(self._help_bars[mode_name])

        for mode, help_bar in self._help_bars.items():
            if mode != mode_name and help_bar is not None:
                help_bar.remove()
                self._help_bars[mode] = None

    def _switch_mode(self, create_fn, mode_name: str):
        """Central mode-switch helper with widget caching for fast ARM mode switching.

        On the first visit to a mode the widget is created and mounted, then
        stored in _mode_cache.  On subsequent visits the cached widget is made
        visible again (display = True) without any widget-tree reconstruction,
        cutting the mode-switch cost from ~300 ms to a single event-loop tick.

        Lifecycle hooks on mode widgets (all optional):
          on_mode_pause()  - called when hiding a mode (stop timers, clear MIDI)
          on_mode_resume() - called when showing a cached mode (restart timers, re-register MIDI)

        Always silences the synth before switching so notes held in the outgoing
        mode cannot bleed into the incoming mode.
        """
        # Silence any held notes before switching.
        self.app_context["synth_engine"].soft_all_notes_off()

        content = self.query_one("#content-area")
        current_mode = self.app_context.get("current_mode")

        # Pause and hide the currently active mode widget.
        if current_mode and current_mode != mode_name and current_mode in self._mode_cache:
            old_widget = self._mode_cache[current_mode]
            if hasattr(old_widget, "on_mode_pause"):
                old_widget.on_mode_pause()
            old_widget.display = False

        # Update current mode tracking immediately.
        self.app_context["current_mode"] = mode_name

        if mode_name in self._mode_cache:
            # Fast path: cached widget — make it visible immediately so Textual
            # renders it on the next frame, then defer the resume/focus to the
            # following tick.  This lets the mode appear on screen before the
            # (potentially heavier) on_mode_resume work runs, giving a snappier
            # perceived response especially on ARM with complex widget trees.
            cached = self._mode_cache[mode_name]
            cached.display = True
            self._apply_help_bars(mode_name)
            def _resume_cached(widget=cached):
                if hasattr(widget, "on_mode_resume"):
                    widget.on_mode_resume()
                if hasattr(widget, "can_focus") and widget.can_focus:
                    widget.focus()
            self.call_later(_resume_cached)
        else:
            # First visit: create, mount, and cache the widget.
            # Deferred so widget construction does not block the audio thread.
            def mount_new_mode():
                """Create and cache the mode widget on first visit."""
                mode_widget = create_fn()
                self._mode_cache[mode_name] = mode_widget
                content.mount(mode_widget)
                self._apply_help_bars(mode_name)
                if hasattr(mode_widget, "can_focus") and mode_widget.can_focus:
                    mode_widget.focus()

            self.call_later(mount_new_mode)

    def action_show_piano(self, save_history=True):
        """Show piano mode."""
        if self.app_context.get("current_mode") == "piano":
            return
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_piano"], "piano")

    def action_show_compendium(self, save_history=True):
        """Show compendium mode."""
        if self.app_context.get("current_mode") == "compendium":
            return
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_compendium"], "compendium")

    def action_show_synth(self, save_history=True):
        """Show synth mode."""
        if self.app_context.get("current_mode") == "synth":
            return
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_synth"], "synth")

    def action_show_metronome(self, save_history=True):
        """Show metronome mode."""
        if self.app_context.get("current_mode") == "metronome":
            return
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_metronome"], "metronome")

    def action_show_tambor(self, save_history=True):
        """Show Tambor drum machine mode."""
        if self.app_context.get("current_mode") == "tambor":
            return
        if save_history:
            self._record_history()
        self._switch_mode(self.app_context["create_tambor"], "tambor")

    def action_show_config(self):
        """Show config modal."""
        # Prevent opening a second config if one is already on the screen stack.
        for screen in self.app.screen_stack:
            if isinstance(screen, ConfigMode):
                return
        # Remember current mode
        self.app_context["mode_before_config"] = self.app_context["current_mode"]

        def on_closed(result):
            # Update footer
            self.app.update_sub_title()

            # Silence any notes that may have been left held before config opened
            engine = self.app_context.get("synth_engine")
            if engine is not None:
                engine.all_notes_off()

            # Reopen MIDI device; cancel any pending auto-reconnect poller.
            self.app._stop_midi_reconnect_polling()
            selected = self.app_context["device_manager"].get_selected_device()
            if selected:
                self.app_context["midi_handler"].close_device()
                self.app_context["midi_handler"].open_device(selected)

            # Return to previous mode
            previous_mode = self.app_context.get("mode_before_config", "main_menu")
            if previous_mode == "piano":
                self.action_show_piano(save_history=False)
            elif previous_mode == "compendium":
                self.action_show_compendium(save_history=False)
            elif previous_mode == "synth":
                self.action_show_synth(save_history=False)
            elif previous_mode == "metronome":
                self.action_show_metronome(save_history=False)
            elif previous_mode == "tambor":
                self.action_show_tambor(save_history=False)
            else: # Defaults to main_menu
                self.action_show_main_menu(save_history=False)

        def on_audio_device_change(new_device_index):
            """Restart the audio subprocess with the newly selected output device."""
            # Translate -2 (System Default sentinel) to None for PyAudio.
            actual_index = None if new_device_index in (-2, None) else new_device_index
            engine = self.app_context["synth_engine"]
            engine.all_notes_off()
            engine.restart_with_device(actual_index)

        def on_buffer_size_change(new_buffer_size):
            """Restart the audio subprocess with the newly selected buffer size."""
            engine = self.app_context["synth_engine"]
            engine.all_notes_off()
            engine.restart_with_buffer_size(new_buffer_size)

        def on_oversampling_change(enabled):
            """Restart the audio subprocess with the new oversampling setting."""
            engine = self.app_context["synth_engine"]
            engine.all_notes_off()
            engine.restart_with_oversampling(enabled)

        config = ConfigMode(
            self.app_context["device_manager"],
            self.app_context["config_manager"],
            on_audio_device_change=on_audio_device_change,
            on_buffer_size_change=on_buffer_size_change,
            on_oversampling_change=on_oversampling_change,
            gamepad_handler=self.app_context.get("gamepad_handler"),
        )
        self.app.push_screen(config, on_closed)

    def action_quit_app(self):
        """Quit with confirmation."""
        # Prevent stacking a second dialog if one is already open.
        for screen in self.app.screen_stack:
            if isinstance(screen, ConfirmationDialog):
                return

        def check_quit(result):
            if result:
                self.app.exit()

        gp = self.app_context.get("gamepad_handler")
        self.app.push_screen(ConfirmationDialog("Quit Acordes?", gamepad_handler=gp), check_quit)


class AcordesApp(App):
    """MIDI Piano TUI Application."""

    VERSION = "1.11.0 - Analogue"
    ENABLE_COMMAND_PALETTE = False  # Disable command palette (Ctrl+Backslash)
    CSS = """
    """

    def __init__(self):
        super().__init__()
        self.title = f"Acordes v{self.VERSION}"
        # Initialize config and non-audio components immediately.
        self.config_manager = ConfigManager()
        self.device_manager = MIDIDeviceManager(self.config_manager)
        self.midi_handler = MIDIInputHandler(config_manager=self.config_manager)
        self.chord_library = ChordLibrary()
        self.chord_detector = ChordDetector(chord_library=self.chord_library)

        # Audio engine is created lazily: only once the audio output device is known.
        # On first launch (no saved device) the engine starts after config completes.
        # On subsequent launches the saved device index is used immediately.
        self.synth_engine = None

        # Register disconnect handler.
        self.midi_handler._disconnect_callback = self._on_midi_disconnect
        # Timer for auto-reconnect polling after MIDI disconnect; None when idle.
        self._midi_reconnect_timer = None

        # Gamepad handler: detect and connect on startup; gracefully absent if no
        # controller is plugged in.  Polling is started in MainScreen.on_mount().
        self.gamepad_handler = GamepadHandler()
        if not self.gamepad_handler.connect():
            print("[gamepad] no controller detected — gamepad input unavailable",
                  file=sys.stderr)

        # App context shared with MainScreen and all modes.
        # synth_engine is None until _start_audio_engine() is called.
        self.app_context = {
            "device_manager": self.device_manager,
            "midi_handler": self.midi_handler,
            "chord_detector": self.chord_detector,
            "chord_library": self.chord_library,
            "synth_engine": self.synth_engine,
            "config_manager": self.config_manager,
            "gamepad_handler": self.gamepad_handler,
            "create_main_menu": self._create_main_menu_mode,
            "create_piano": self._create_piano_mode,
            "create_compendium": self._create_compendium_mode,
            "create_synth": self._create_synth_mode,
            "create_metronome": self._create_metronome_mode,
            "create_tambor": self._create_tambor_mode,
            "current_mode": "main_menu",
            "mode_before_config": "main_menu",
        }

    def _start_audio_engine(self, device_index=None):
        """Create the audio subprocess with the given device index and show the loading screen.

        device_index values:
          -2  = System Default (OS/PipeWire selects the output device)
          -1  = No Audio (engine runs silently, no PyAudio stream)
          None = same as -2 (legacy; treated as system default)
          >=0 = specific PyAudio device index
        """
        # Translate -2 sentinel to None so PyAudio uses the system default.
        actual_index = None if device_index in (-2, None) else device_index

        buffer_size = self.config_manager.get_buffer_size()
        audio_backend = self.config_manager.get_audio_backend()
        enable_oversampling = self.config_manager.get_oversampling_enabled()
        self.synth_engine = SynthEngineProxy(output_device_index=actual_index, buffer_size=buffer_size, audio_backend=audio_backend, enable_oversampling=enable_oversampling)
        self.app_context["synth_engine"] = self.synth_engine

        # Auto-open saved MIDI device now that we have an engine to pair with.
        selected_device = self.device_manager.get_selected_device()
        if selected_device and not self.midi_handler.is_device_open():
            self.midi_handler.open_device(selected_device)

        loading = LoadingScreen(self.synth_engine, self._after_engine_ready)
        self.push_screen(loading)

    def on_mount(self):
        """Called when app mounts.

        First launch (no saved audio device): show config so the user can pick
        their audio output and MIDI device before the engine starts.

        Subsequent launches: validate that the saved audio device index is still
        present in the system. If the device is gone (e.g. USB interface unplugged),
        clear the saved device and show config mode so the user can pick a new one.
        """
        self.update_sub_title()
        saved_audio_index = self.config_manager.get_audio_device_index()

        # Sentinel values -1 (No Audio) and -2 (System Default) are always valid;
        # skip hardware enumeration for them. Only validate real device indices (>=0).
        if saved_audio_index is not None and saved_audio_index >= 0:
            available = {idx for idx, _ in list_output_devices()}
            if saved_audio_index not in available:
                # Device no longer present — clear saved choice and re-configure.
                saved_name = self.config_manager.get_audio_device_name() or str(saved_audio_index)
                self.config_manager.set_audio_device(None, None)
                saved_audio_index = None
                self._missing_audio_device_name = saved_name
            else:
                self._missing_audio_device_name = None
        else:
            self._missing_audio_device_name = None

        if saved_audio_index is None:
            # No valid audio device: first launch or device went missing.
            def on_config_closed(result):
                # Auto-save backend if user closed without choosing one.
                # Use the OS recommendation rather than a generic "System Default"
                # so the engine starts on the best available driver automatically.
                if self.config_manager.get_audio_backend() is None:
                    from music.synth_engine import recommended_audio_backend
                    self.config_manager.set_audio_backend(recommended_audio_backend())
                chosen_index = self.config_manager.get_audio_device_index()
                if chosen_index is None:
                    # User closed config without selecting audio device.
                    # Default to "System Default" and save it.
                    self.config_manager.set_audio_device(-2, "System Default")
                    chosen_index = -2
                # Defer engine start to the next event loop tick so the config
                # screen is fully dismissed before the audio subprocess spawns.
                # On macOS (Python 3.12+) spawning a process while Textual's
                # asyncio sockets are still open causes ValueError: bad value(s)
                # in fds_to_keep.
                self.call_later(self._start_audio_engine, chosen_index)
            config = ConfigMode(self.device_manager, self.config_manager)
            self.push_screen(config, on_config_closed)
        else:
            # Saved device confirmed present — start engine directly.
            self._start_audio_engine(saved_audio_index)

    def _after_engine_ready(self):
        """Called by LoadingScreen once the audio process signals ready."""
        self.pop_screen()  # dismiss loading screen

        # Push MainScreen; it always shows first so config (if needed) overlays on top.
        main_screen = MainScreen(self.app_context)
        self.push_screen(main_screen)

        # Store current audio backend so we can detect if user changed it in config mode
        original_backend = self.config_manager.get_audio_backend()

        # Show config only if MIDI device has not been configured yet.
        # Audio device is already configured at this point.
        if not self.config_manager.is_midi_device_configured():
            def on_config_closed(result):
                # If user closed config without selecting MIDI device, default to "No MIDI Device"
                if not self.config_manager.is_midi_device_configured():
                    self.device_manager.select_device(None)

                # Check if audio backend was changed and restart engine if needed
                current_backend = self.config_manager.get_audio_backend()
                if current_backend != original_backend:
                    # Backend changed: restart engine with new backend
                    self.synth_engine.restart_with_backend(current_backend)

                self.update_sub_title()
                selected = self.device_manager.get_selected_device()
                if selected and not self.midi_handler.is_device_open():
                    self.midi_handler.open_device(selected)
            config = ConfigMode(self.device_manager, self.config_manager)
            self.push_screen(config, on_config_closed)

        self.update_sub_title()

    def update_sub_title(self):
        """Update sub title with MIDI device and audio output info."""
        midi = self.device_manager.get_selected_device()
        audio_index = self.config_manager.get_audio_device_index()
        audio_name = self.config_manager.get_audio_device_name() or ""

        if audio_index == -1:
            audio_str = "No Audio"
        elif audio_index == -2 or audio_index is None:
            audio_str = "System Default"
        else:
            audio_str = audio_name or f"Device {audio_index}"

        if midi:
            self.sub_title = f"🎹 {midi}  |  🔊 {audio_str}"
        else:
            self.sub_title = f"⚠ No MIDI device (press C)  |  🔊 {audio_str}"

    def _on_midi_disconnect(self):
        """Called when the MIDI port errors out (device unplugged mid-session).

        Soft-silences the synth (preserves looper state) and shows a toast
        notification. A background reconnect poller then watches for the
        device to reappear on USB and reconnects automatically.
        Uses call_later so all UI work happens on the Textual event loop,
        not on the poll-timer thread that invoked this callback.
        """
        # Soft-silence: stop all notes but do NOT kill the looper state machine.
        if self.synth_engine:
            self.synth_engine.soft_all_notes_off()

        self.call_later(self._handle_midi_disconnect_ui)

    def _handle_midi_disconnect_ui(self):
        """UI-thread side of MIDI disconnect: notify user and start auto-reconnect."""
        self.update_sub_title()
        self.notify(
            "MIDI controller disconnected. Reconnecting automatically...",
            severity="warning",
            timeout=8,
        )
        self._start_midi_reconnect_polling()

    def _start_midi_reconnect_polling(self):
        """Start a 2-second background timer that auto-reconnects the MIDI device."""
        # Guard: don't stack multiple timers if disconnect fires more than once.
        if getattr(self, "_midi_reconnect_timer", None) is not None:
            return
        self._midi_reconnect_timer = self.set_interval(2.0, self._try_midi_reconnect)

    def _try_midi_reconnect(self):
        """Poll for the saved MIDI device; reconnect and stop the timer when found."""
        if self.midi_handler.is_device_open():
            # Already reconnected (e.g. via config screen); cancel the poller.
            self._stop_midi_reconnect_polling()
            return

        saved_device = self.device_manager.get_selected_device()
        if not saved_device:
            return

        try:
            import mido
            available = mido.get_input_names()
        except Exception:
            return

        if saved_device in available:
            if self.midi_handler.open_device(saved_device):
                self._stop_midi_reconnect_polling()
                self.update_sub_title()
                self.notify(
                    f"MIDI reconnected: {saved_device}",
                    severity="information",
                    timeout=4,
                )

    def _stop_midi_reconnect_polling(self):
        """Cancel the auto-reconnect poller if it is running."""
        timer = getattr(self, "_midi_reconnect_timer", None)
        if timer is not None:
            timer.stop()
            self._midi_reconnect_timer = None

    def _create_main_menu_mode(self, main_screen):
        """Create main menu widget."""
        return MainMenuMode(main_screen)

    def _create_piano_mode(self):
        """Create piano mode widget."""
        selected = self.device_manager.get_selected_device()
        if selected and not self.midi_handler.is_device_open():
            self.midi_handler.open_device(selected)

        return PianoMode(self.midi_handler, self.chord_detector, self.synth_engine,
                         gamepad_handler=self.gamepad_handler)

    def _create_compendium_mode(self):
        """Create compendium mode widget."""
        return CompendiumMode(self.chord_library, self.synth_engine,
                              gamepad_handler=self.gamepad_handler)

    def _create_synth_mode(self):
        """Create synth mode widget."""
        selected = self.device_manager.get_selected_device()
        if selected and not self.midi_handler.is_device_open():
            self.midi_handler.open_device(selected)

        return SynthMode(self.midi_handler, self.synth_engine, self.config_manager,
                         gamepad_handler=self.gamepad_handler)

    def _create_metronome_mode(self):
        """Create metronome mode widget."""
        return MetronomeMode(self.config_manager, self.synth_engine,
                             gamepad_handler=self.gamepad_handler)

    def _create_tambor_mode(self):
        """Create Tambor drum machine mode widget."""
        return TamborMode(
            config_manager=self.config_manager,
            synth_engine=self.synth_engine,
            midi_handler=self.midi_handler,
            gamepad_handler=self.gamepad_handler,
        )

    def on_unmount(self):
        """Clean up on exit."""
        self.midi_handler.close_device()
        # Flush any pending deferred config write so settings are not lost on exit.
        self.config_manager.flush()
        # Clear the terminal screen
        os.system('cls' if os.name == 'nt' else 'clear')


def _detect_small_display() -> bool:
    """Return True when running on ARM Linux (OStra / Raspberry Pi).

    The Pi's /dev/fb0 virtual size is 790x600 (bcm2708_fb internal resolution)
    even though the physical TFT-LCD is 480x320 — fbcp scales it on the way out.
    Checking the virtual framebuffer size therefore does not reliably identify
    the small display. ARM platform detection is the correct signal here:
    OStra only ever runs on ARM, and desktop always runs on x86/x64.

    Override with ACORDES_UI=simple (force Pygame) or ACORDES_UI=advanced
    (force Textual) regardless of platform.
    """
    override = os.environ.get("ACORDES_UI", "")
    if override == "advanced":
        return False
    if override == "simple":
        return True
    import platform as _p
    return _p.machine() in ("armv7l", "aarch64")


def _run_arm_ui() -> None:
    """Initialize shared components and launch the ARM Pygame UI."""
    from arm_ui.app import ArmApp
    from music.preset_manager import PresetManager

    config_manager = ConfigManager()
    device_manager = MIDIDeviceManager(config_manager)
    midi_handler = MIDIInputHandler(config_manager=config_manager)
    chord_library = ChordLibrary()
    chord_detector = ChordDetector(chord_library=chord_library)
    gamepad_handler = GamepadHandler()
    gamepad_handler.connect()
    preset_manager = PresetManager()

    ArmApp(
        config_manager=config_manager,
        device_manager=device_manager,
        midi_handler=midi_handler,
        chord_detector=chord_detector,
        gamepad_handler=gamepad_handler,
        preset_manager=preset_manager,
    ).run()


def main():
    """Main entry point."""
    use_arm_ui = _detect_small_display() or os.environ.get("ACORDES_UI") == "simple"
    if use_arm_ui:
        _run_arm_ui()
    else:
        AcordesApp().run()


if __name__ == "__main__":
    # Required for PyInstaller packaging on Windows (spawn creates a frozen subprocess).
    # Safe to call on all platforms — no-op on Linux/macOS.
    multiprocessing.freeze_support()
    # Explicit spawn on all platforms for consistent cross-platform behavior.
    # Windows uses spawn by default anyway; this makes Linux/macOS match.
    multiprocessing.set_start_method('spawn')

    # macOS + Python 3.12 fix: pre-warm the multiprocessing resource tracker
    # before Textual starts and captures sys.stderr.
    #
    # Python 3.12's resource_tracker.ensure_running() calls sys.stderr.fileno()
    # to pass stderr to the tracker subprocess. Textual intercepts sys.stderr and
    # its virtual stream returns fileno() = -1.  When multiprocessing.Queue() is
    # first called inside a Textual callback (on_mount), the resource tracker gets
    # -1 as a file descriptor, causing:
    #   ValueError: bad value(s) in fds_to_keep
    #
    # By creating a throwaway Queue here — while real stderr is still intact —
    # we force the resource tracker to start with a valid stderr fd before Textual
    # takes over.  Subsequent Queue() calls inside the app reuse the already-running
    # tracker and never hit the bad-fd path.
    if sys.platform == "darwin":
        _warmup_q = multiprocessing.Queue()
        _warmup_q.close()
        del _warmup_q

    main()
