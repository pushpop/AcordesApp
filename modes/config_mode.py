# ABOUTME: Configuration screen for audio backend, audio device, buffer size, MIDI input, and velocity curve.
# ABOUTME: Appears on first launch or when user presses C from the main app.
"""Audio backend, audio device, buffer size, MIDI device, and velocity curve configuration screen."""
import platform
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, ListView, ListItem, Label
from textual.binding import Binding
from components.header_widget import HeaderWidget
from typing import TYPE_CHECKING, Optional, Callable, List, Tuple

if TYPE_CHECKING:
    from midi.device_manager import MIDIDeviceManager
    from config_manager import ConfigManager


class ConfigMode(Screen):
    """Screen for configuring audio backend, audio device, buffer size, MIDI devices, and velocity curves."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("r", "refresh_devices", "Refresh", show=True),
        Binding("space", "select_item", "Select", show=True),
        Binding("tab", "toggle_list_focus", "Switch list", show=True),
    ]

    CSS = """
    ConfigMode {
        align: center middle;
    }

    #config-container {
        width: 100%;
        height: auto;
        border: thick #ffd700;
        background: #1a1a1a;
        padding: 1 2;
    }

    /* Top row: backend (left) + audio device (center) + buffer size (right) */
    #top-row {
        width: 100%;
        height: auto;
    }

    /* Bottom row: MIDI (left) + velocity curve (right) */
    #bottom-row {
        width: 100%;
        height: auto;
        margin-top: 1;
    }

    #backend-section {
        width: 1fr;
        height: auto;
        padding-right: 1;
    }

    #audio-section {
        width: 1fr;
        height: auto;
        padding-left: 1;
        padding-right: 1;
    }

    #buffer-section {
        width: 1fr;
        height: auto;
        padding-left: 1;
    }

    #device-section {
        width: 1fr;
        height: auto;
        padding-right: 1;
    }

    #curve-section {
        width: 1fr;
        height: auto;
        padding-left: 1;
    }

    #backend-label {
        width: 100%;
        color: #ffd700;
        text-style: bold;
        margin-top: 1;
    }

    #backend-list {
        width: 100%;
        height: 8;
        border: solid #ffd700;
        margin: 0 0 0 0;
    }

    #selected-backend {
        width: 100%;
        content-align: left middle;
        color: #00ff00;
        margin: 0;
    }

    #audio-label {
        width: 100%;
        color: #ffd700;
        text-style: bold;
        margin-top: 1;
    }

    #audio-list {
        width: 100%;
        height: 8;
        border: solid #ffd700;
        margin: 0 0 0 0;
    }

    #selected-audio {
        width: 100%;
        content-align: left middle;
        color: #00ff00;
        margin: 0;
    }

    #buffer-label {
        width: 100%;
        color: #ffd700;
        text-style: bold;
        margin-top: 1;
    }

    #buffer-list {
        width: 100%;
        height: 8;
        border: solid #ffd700;
        margin: 0 0 0 0;
    }

    #selected-buffer {
        width: 100%;
        content-align: left middle;
        color: #00ff00;
        margin: 0;
    }

    #device-label {
        width: 100%;
        color: #ffd700;
        text-style: bold;
        margin-top: 1;
    }

    #device-list {
        width: 100%;
        height: 8;
        border: solid #ffd700;
        margin: 0 0 0 0;
    }

    #selected-device {
        width: 100%;
        content-align: left middle;
        color: #00ff00;
        margin: 0;
    }

    #curve-label {
        width: 100%;
        color: #ffd700;
        text-style: bold;
        margin-top: 1;
    }

    #curve-list {
        width: 100%;
        height: 8;
        border: solid #ffd700;
        margin: 0 0 0 0;
    }

    #selected-curve {
        width: 100%;
        content-align: left middle;
        color: #00ff00;
        margin: 0;
    }

    #instructions {
        width: 100%;
        content-align: center middle;
        color: #888888;
        text-style: italic;
        margin-top: 1;
    }
    """

    # Buffer sizes offered in the UI. ARM (bcm2835 headphone jack): 2048 (~46ms)
    # is the new floor now that scipy C-level filters replaced the Python loops.
    # 4096 (~93ms) and 8192 (~186ms) remain available for very loaded systems.
    # Desktop supports smaller buffers for lower latency.
    _IS_ARM = platform.machine() in ("armv7l", "aarch64")
    BUFFER_SIZES = [2048, 4096, 8192] if _IS_ARM else [128, 256, 480, 512, 1024, 2048]

    # Ordered list of list IDs for LB/RB cycling.
    # Oversampling list is desktop-only; ARM always has it disabled.
    _LIST_IDS = (
        ["#backend-list", "#audio-list", "#buffer-list", "#device-list", "#curve-list", "#oversample-list"]
        if not platform.machine() in ("armv7l", "aarch64")
        else ["#backend-list", "#audio-list", "#buffer-list", "#device-list", "#curve-list"]
    )

    def __init__(
        self,
        device_manager: 'MIDIDeviceManager',
        config_manager: 'ConfigManager',
        on_audio_device_change: Optional[Callable[[int], None]] = None,
        on_buffer_size_change: Optional[Callable[[int], None]] = None,
        on_oversampling_change: Optional[Callable[[bool], None]] = None,
        gamepad_handler=None,
    ):
        super().__init__()
        self.device_manager = device_manager
        self.config_manager = config_manager
        self._gamepad_handler = gamepad_handler
        # Callback invoked when user selects a new audio device (engine is running).
        # If None, audio selection is saved to config only (engine not yet running).
        self.on_audio_device_change = on_audio_device_change
        # Callback invoked when user selects a new buffer size (engine is running).
        # If None, buffer size is saved to config only (engine not yet running).
        self.on_buffer_size_change = on_buffer_size_change
        # Callback invoked when user toggles oversampling (desktop only).
        self.on_oversampling_change = on_oversampling_change

        # Audio backend state: list of (name, hostapi_index) tuples
        self.backends: List[Tuple[str, int]] = []
        # Use saved backend if available; otherwise pre-select the OS recommendation
        # so the user sees the best option highlighted on first launch.
        saved_backend = config_manager.get_audio_backend()
        if saved_backend is not None:
            self.pending_backend: Optional[str] = saved_backend
        else:
            from music.synth_engine import recommended_audio_backend
            self.pending_backend: Optional[str] = recommended_audio_backend()

        # Audio device state: list of (device_index, name) tuples
        self.audio_devices: List[Tuple[int, str]] = []
        self.pending_audio_index: Optional[int] = config_manager.get_audio_device_index()

        # Buffer size state
        self.pending_buffer_size: int = config_manager.get_buffer_size()

        # MIDI device state
        self.devices: List[str] = []
        self.pending_device: Optional[str] = None

        self.velocity_curves = ["Linear", "Soft", "Normal", "Strong", "Very Strong"]
        self.pending_curve = config_manager.get_velocity_curve()

        # Oversampling state (desktop only)
        self.pending_oversampling: bool = config_manager.get_oversampling_enabled()

    def compose(self):
        """Compose the config mode layout as a 3x2 grid."""
        yield Header()
        with Vertical(id="config-container"):
            yield HeaderWidget(title="CONFIGURATION", subtitle="Audio Backend, Device, Buffer, MIDI & Velocity")

            # Top row: Audio Backend (left) | Audio Output Device (center) | Buffer Size (right)
            with Horizontal(id="top-row"):
                with Vertical(id="backend-section"):
                    yield Label("AUDIO BACKEND", id="backend-label")
                    yield ListView(id="backend-list")
                    yield Label("", id="selected-backend")

                with Vertical(id="audio-section"):
                    yield Label("AUDIO OUTPUT DEVICE", id="audio-label")
                    yield ListView(id="audio-list")
                    yield Label("", id="selected-audio")

                with Vertical(id="buffer-section"):
                    yield Label("BUFFER SIZE", id="buffer-label")
                    yield ListView(id="buffer-list")
                    yield Label("", id="selected-buffer")

            # Bottom row: MIDI Input Device | Velocity Curve | Oversampling (desktop only)
            with Horizontal(id="bottom-row"):
                with Vertical(id="device-section"):
                    yield Label("MIDI INPUT DEVICE", id="device-label")
                    yield ListView(id="device-list")
                    yield Label("", id="selected-device")

                with Vertical(id="curve-section"):
                    yield Label("VELOCITY CURVE", id="curve-label")
                    yield ListView(id="curve-list")
                    yield Label("", id="selected-curve")

                if not self._IS_ARM:
                    with Vertical(id="oversample-section"):
                        yield Label("OVERSAMPLING (2×)", id="oversample-label")
                        yield ListView(id="oversample-list")
                        yield Label("", id="selected-oversample")

            yield Label(
                "Tab: Switch section | ↑↓: Navigate | Space: Select | R: Refresh | Esc: Close",
                id="instructions"
            )
        yield Footer()

    def _get_gamepad_handler(self):
        """Return the gamepad handler from the app or the constructor parameter."""
        gp = getattr(self.app, "gamepad_handler", None)
        if gp is None:
            gp = self._gamepad_handler
        return gp

    def on_mount(self):
        """Called when screen is mounted."""
        self.pending_device = self.device_manager.get_selected_device()
        self.refresh_backend_list()
        self.refresh_audio_list()
        self.refresh_buffer_list()
        self.refresh_device_list()
        self.refresh_curve_list()
        if not self._IS_ARM:
            self.refresh_oversample_list()

        # Start focus on backend list so user picks driver first
        self.query_one("#backend-list", ListView).focus()
        self._register_gamepad_callbacks()

    def on_unmount(self):
        """Called when config screen is dismissed.
        Gamepad callbacks are NOT cleared here because on_closed fires before
        on_unmount in Textual — the returning mode's on_mode_resume already
        re-registers callbacks via _register_gamepad_callbacks(), and that
        method calls gp.clear_callbacks() itself before re-registering.
        Clearing here would wipe the freshly registered mode callbacks.
        """

    def _register_gamepad_callbacks(self):
        """Register gamepad callbacks for config screen navigation."""
        gp = self._get_gamepad_handler()
        if gp is None:
            return
        from gamepad.actions import GP
        gp.clear_callbacks()
        gp.set_button_callback(GP.DPAD_UP,    self._gp_nav_up)
        gp.set_button_callback(GP.DPAD_DOWN,  self._gp_nav_down)
        gp.set_button_callback(GP.LB,         self._gp_prev_list)
        gp.set_button_callback(GP.RB,         self._gp_next_list)
        gp.set_button_callback(GP.CONFIRM,    self.action_select_item)
        gp.set_button_callback(GP.BACK,       self._gp_close)
        gp.set_button_callback(GP.BACK_BTN,   self._gp_close)

    def _gp_nav_up(self):
        """Move cursor up in the focused list."""
        lv = self.query_one(self._focused_list_id(), ListView)
        lv.action_cursor_up()

    def _gp_nav_down(self):
        """Move cursor down in the focused list."""
        lv = self.query_one(self._focused_list_id(), ListView)
        lv.action_cursor_down()

    def _gp_prev_list(self):
        """Move focus to the previous list (LB)."""
        current = self._focused_list_id()
        try:
            idx = self._LIST_IDS.index(current)
        except ValueError:
            idx = 0
        prev_id = self._LIST_IDS[(idx - 1) % len(self._LIST_IDS)]
        self.query_one(prev_id, ListView).focus()

    def _gp_next_list(self):
        """Move focus to the next list (RB), same as Tab."""
        self.action_toggle_list_focus()

    def _gp_close(self):
        """Close the config screen via B button."""
        self.dismiss()

    # ── Backend ──────────────────────────────────────────────────────────────

    def refresh_backend_list(self):
        """Populate the audio backend list from available PortAudio host APIs."""
        from music.synth_engine import list_audio_backends
        list_view = self.query_one("#backend-list", ListView)
        list_view.clear()

        self.backends = list_audio_backends()

        # Prepend "System Default" so the user can opt out of backend selection
        all_backends = [("System Default", -1)] + self.backends

        for name, hid in all_backends:
            marker = "☑" if name == self.pending_backend else "☐"
            list_view.append(ListItem(Label(f"{marker} {name}")))

        # Store the full list including System Default for index lookup
        self._all_backends = all_backends
        self._update_backend_label()

    def _select_audio_backend(self):
        """Save the highlighted backend and refresh the device list to match."""
        list_view = self.query_one("#backend-list", ListView)
        if list_view.index is None or not self._all_backends:
            return
        if not (0 <= list_view.index < len(self._all_backends)):
            return

        name, _hid = self._all_backends[list_view.index]
        self.pending_backend = name
        self.config_manager.set_audio_backend(name)

        # Refresh device list filtered to the newly chosen backend
        self.refresh_backend_list()
        self.refresh_audio_list()

    def _setup_flexasio_config(self):
        """Create or update FlexASIO.toml with Acordes-optimized settings (Windows only).

        Generates at C:\\Users\\<username>\\AppData\\Local\\FlexASIO.toml with settings
        matched to the current Acordes engine configuration (sample rate, buffer size).
        Triggered automatically when the user selects a FlexASIO device in the audio list.
        """
        try:
            from music.flexasio_config import create_or_update_flexasio_config
            import platform

            # FlexASIO only works on Windows
            if platform.system() != "Windows":
                return

            # Get engine settings from the synth engine (if available in app context)
            sample_rate = 48000  # default
            buffer_size = self.pending_buffer_size
            synth_engine = self.app.synth_engine if hasattr(self.app, 'synth_engine') else None
            if synth_engine:
                # Read actual engine settings if synth engine is running
                if hasattr(synth_engine, 'sample_rate'):
                    sample_rate = synth_engine.sample_rate

            # Silently create the config file — FlexASIO reads it on next restart
            create_or_update_flexasio_config(sample_rate=sample_rate, buffer_samples=buffer_size)

        except Exception:
            # Silently fail if FlexASIO config setup has issues (e.g., permission denied)
            pass

    def _update_backend_label(self):
        """Update the audio backend status label."""
        label = self.query_one("#selected-backend", Label)
        if self.pending_backend:
            label.update(f"Selected: {self.pending_backend}")
        else:
            label.update("No backend selected — select one above first")

    # ── Audio Device ─────────────────────────────────────────────────────────

    def refresh_audio_list(self):
        """Refresh the audio device list, filtered by the currently selected backend.

        Sentinel values always prepended:
          -2 = System Default  (OS picks the output device)
          -1 = No Audio        (engine runs silently)
        When a specific backend is selected, only devices from that backend are shown.
        """
        from music.synth_engine import list_output_devices, list_output_devices_for_backend
        list_view = self.query_one("#audio-list", ListView)
        list_view.clear()

        # Use backend-filtered list when a real backend is chosen
        if self.pending_backend and self.pending_backend != "System Default":
            hardware = list_output_devices_for_backend(self.pending_backend)
        else:
            hardware = list_output_devices()

        self.audio_devices = [(-2, "System Default"), (-1, "No Audio")] + hardware

        for idx, name in self.audio_devices:
            marker = "☑" if idx == self.pending_audio_index else "☐"
            list_view.append(ListItem(Label(f"{marker} {name}")))

        self._update_audio_label()

    def _select_audio_device(self):
        """Save the highlighted audio output device and optionally restart the engine."""
        list_view = self.query_one("#audio-list", ListView)
        if list_view.index is None or not self.audio_devices:
            return
        if not (0 <= list_view.index < len(self.audio_devices)):
            return

        idx, name = self.audio_devices[list_view.index]
        self.pending_audio_index = idx
        self.config_manager.set_audio_device(idx, name)
        self.refresh_audio_list()

        # Auto-generate FlexASIO.toml when user selects a FlexASIO device.
        # FlexASIO appears as a device under the ASIO backend, not as a backend itself.
        if "FlexASIO" in name:
            self._setup_flexasio_config()

        # If the engine is already running, trigger a restart with the new device
        if self.on_audio_device_change is not None:
            self.on_audio_device_change(idx)

    def _update_audio_label(self):
        """Update the audio output device status label."""
        label = self.query_one("#selected-audio", Label)
        if self.pending_audio_index is not None:
            name = next(
                (n for i, n in self.audio_devices if i == self.pending_audio_index),
                self.config_manager.get_audio_device_name() or "Unknown"
            )
            label.update(f"Selected: {name}")
        else:
            label.update("No audio device selected")

    # ── Buffer Size ───────────────────────────────────────────────────────────

    def refresh_buffer_list(self):
        """Populate the buffer size list with standard options and latency hints.

        Note: ASIO4ALL may not support all buffer sizes. If the actual buffer size
        differs from your selection, check the startup console output for diagnostics
        (it will print the negotiated blocksize). Consider using a native ASIO driver
        for full buffer size control, or adjust to a size your WDM driver supports.
        """
        list_view = self.query_one("#buffer-list", ListView)
        list_view.clear()

        # ARM uses 44100 Hz (bcm2835 native); desktop uses 48000 Hz.
        import platform as _plat
        sample_rate = 44100 if _plat.machine() in ("armv7l", "aarch64") else 48000
        for size in self.BUFFER_SIZES:
            latency_ms = (size / sample_rate) * 1000
            marker = "☑" if size == self.pending_buffer_size else "☐"
            list_view.append(ListItem(Label(f"{marker}  {size:<6}  ({latency_ms:.1f} ms)")))

        self._update_buffer_label()

    def _select_buffer_size(self):
        """Save the highlighted buffer size and optionally restart the engine."""
        list_view = self.query_one("#buffer-list", ListView)
        if list_view.index is None:
            return
        if not (0 <= list_view.index < len(self.BUFFER_SIZES)):
            return

        size = self.BUFFER_SIZES[list_view.index]
        self.pending_buffer_size = size
        self.config_manager.set_buffer_size(size)
        self.refresh_buffer_list()

        # If the engine is already running, trigger a restart with the new buffer size
        if self.on_buffer_size_change is not None:
            self.on_buffer_size_change(size)

    def _update_buffer_label(self):
        """Update the buffer size status label."""
        label = self.query_one("#selected-buffer", Label)
        size = self.pending_buffer_size
        sample_rate = 48000
        latency_ms = (size / sample_rate) * 1000
        if self._IS_ARM:
            # Show the effective size the engine will actually use (min 2048 on ARM).
            effective = max(2048, size)
            effective_ms = (effective / sample_rate) * 1000
            if effective != size:
                label.update(f"Selected: {size}  ->  effective: {effective} samples ({effective_ms:.1f} ms)  [ARM minimum]")
            else:
                label.update(f"Selected: {size} samples  ({latency_ms:.1f} ms)")
        else:
            label.update(f"Selected: {size} samples  ({latency_ms:.1f} ms)  [check console if ASIO4ALL shows different size]")

    # ── MIDI Device ──────────────────────────────────────────────────────────

    def refresh_device_list(self):
        """Refresh the list of MIDI input devices."""
        list_view = self.query_one("#device-list", ListView)
        list_view.clear()

        self.devices = self.device_manager.get_input_devices()

        marker = "☑" if self.pending_device is None else "☐"
        list_view.append(ListItem(Label(f"{marker} No MIDI Device")))

        if not self.devices:
            if self.device_manager.last_error:
                list_view.append(ListItem(Label("❌ " + self.device_manager.last_error)))
            else:
                list_view.append(ListItem(Label("(No devices found)")))
        else:
            for device in self.devices:
                marker = "☑" if device == self.pending_device else "☐"
                list_view.append(ListItem(Label(f"{marker} {device}")))

        self._update_device_label()

    def _select_device(self):
        """Apply the highlighted MIDI device."""
        list_view = self.query_one("#device-list", ListView)
        if list_view.index is None:
            return

        if list_view.index == 0:
            self.pending_device = None
            self.device_manager.select_device(None)
        elif 1 <= list_view.index <= len(self.devices):
            selected = self.devices[list_view.index - 1]
            self.pending_device = selected
            self.device_manager.select_device(selected)

        self.refresh_device_list()

    def _update_device_label(self):
        """Update the MIDI device status label."""
        label = self.query_one("#selected-device", Label)
        active = self.device_manager.get_selected_device()
        if self.pending_device and self.pending_device != active:
            label.update(f"Active: {active or 'None'} | Pending: {self.pending_device}")
        elif active:
            label.update(f"Active: {active}")
        else:
            label.update("No device selected")

    # ── Velocity Curve ───────────────────────────────────────────────────────

    def refresh_curve_list(self):
        """Refresh the velocity curve list."""
        list_view = self.query_one("#curve-list", ListView)
        list_view.clear()

        for curve in self.velocity_curves:
            marker = "☑" if curve == self.pending_curve else "☐"
            list_view.append(ListItem(Label(f"{marker} {curve}")))

        self._update_curve_label()

    def _select_curve(self):
        """Apply the highlighted velocity curve."""
        list_view = self.query_one("#curve-list", ListView)
        if list_view.index is not None and 0 <= list_view.index < len(self.velocity_curves):
            selected = self.velocity_curves[list_view.index]
            self.pending_curve = selected
            self.config_manager.set_velocity_curve(selected)
            self.refresh_curve_list()

    def _update_curve_label(self):
        """Update the velocity curve status label."""
        label = self.query_one("#selected-curve", Label)
        label.update(f"Selected: {self.pending_curve}")

    def refresh_oversample_list(self):
        """Refresh the oversampling toggle list (desktop only)."""
        list_view = self.query_one("#oversample-list", ListView)
        list_view.clear()
        for label_text, value in [("On  (2× aliasing reduction)", True),
                                   ("Off (lower CPU usage)", False)]:
            marker = "☑" if value == self.pending_oversampling else "☐"
            list_view.append(ListItem(Label(f"{marker} {label_text}")))
        self._update_oversample_label()

    def _select_oversample(self):
        """Apply the highlighted oversampling choice."""
        list_view = self.query_one("#oversample-list", ListView)
        options = [True, False]
        if list_view.index is not None and 0 <= list_view.index < len(options):
            selected = options[list_view.index]
            self.pending_oversampling = selected
            self.config_manager.set_oversampling_enabled(selected)
            self.refresh_oversample_list()
            if self.on_oversampling_change:
                self.on_oversampling_change(selected)

    def _update_oversample_label(self):
        """Update the oversampling status label."""
        label = self.query_one("#selected-oversample", Label)
        label.update(f"Selected: {'On' if self.pending_oversampling else 'Off'}")

    # ── Navigation ───────────────────────────────────────────────────────────

    def _focused_list_id(self) -> str:
        """Return the ID of whichever list currently has focus."""
        ids = self._LIST_IDS
        for list_id in ids:
            lv = self.query_one(list_id, ListView)
            if self.focused is lv:
                return list_id
        return "#backend-list"

    def action_toggle_list_focus(self):
        """Tab — cycle focus: backend -> audio -> buffer -> midi -> curve -> backend."""
        current = self._focused_list_id()

        if current == "#backend-list":
            next_id = "#audio-list"
            # Auto-highlight current audio selection
            if self.pending_audio_index is not None:
                indices = [i for i, _ in self.audio_devices]
                if self.pending_audio_index in indices:
                    self.query_one("#audio-list", ListView).index = indices.index(self.pending_audio_index)
        elif current == "#audio-list":
            next_id = "#buffer-list"
            # Auto-highlight current buffer size selection
            if self.pending_buffer_size in self.BUFFER_SIZES:
                self.query_one("#buffer-list", ListView).index = self.BUFFER_SIZES.index(self.pending_buffer_size)
        elif current == "#buffer-list":
            next_id = "#device-list"
            # Auto-highlight current MIDI selection
            if self.pending_device is None:
                self.query_one("#device-list", ListView).index = 0
            elif self.pending_device in self.devices:
                self.query_one("#device-list", ListView).index = self.devices.index(self.pending_device) + 1
        elif current == "#device-list":
            next_id = "#curve-list"
            if self.pending_curve in self.velocity_curves:
                self.query_one("#curve-list", ListView).index = self.velocity_curves.index(self.pending_curve)
        elif current == "#curve-list" and not self._IS_ARM:
            next_id = "#oversample-list"
            self.query_one("#oversample-list", ListView).index = 0 if self.pending_oversampling else 1
        else:
            next_id = "#backend-list"
            # Auto-highlight current backend selection
            if self.pending_backend and hasattr(self, '_all_backends'):
                names = [n for n, _ in self._all_backends]
                if self.pending_backend in names:
                    self.query_one("#backend-list", ListView).index = names.index(self.pending_backend)

        self.query_one(next_id, ListView).focus()

    def action_select_item(self):
        """Space — select highlighted item in the focused list."""
        current = self._focused_list_id()
        if current == "#backend-list":
            self._select_audio_backend()
        elif current == "#audio-list":
            self._select_audio_device()
        elif current == "#buffer-list":
            self._select_buffer_size()
        elif current == "#device-list":
            self._select_device()
        elif current == "#curve-list":
            self._select_curve()
        elif current == "#oversample-list":
            self._select_oversample()

    def action_refresh_devices(self):
        """Refresh all device lists."""
        self.refresh_backend_list()
        self.refresh_audio_list()
        self.refresh_device_list()
