# ABOUTME: Main Pygame application loop and screen manager for the ARM Pygame UI.
# ABOUTME: Handles display init, engine startup, gamepad polling, and screen transitions.

import os
import sys
import threading

import pygame

from arm_ui import theme
from arm_ui.fb0_writer import Fb0Writer
from gamepad.actions import GP


class ArmApp:
    """ARM Pygame UI application.

    Manages the Pygame display, main loop, and screen transitions. All shared
    backend components (SynthEngineProxy, GamepadHandler, MIDIInputHandler, etc.)
    are created externally and passed in - this class only owns the UI layer.
    """

    FPS = 60

    def __init__(
        self,
        config_manager,
        device_manager,
        midi_handler,
        chord_detector,
        gamepad_handler,
        preset_manager,
    ) -> None:
        self.config_manager  = config_manager
        self.device_manager  = device_manager
        self.midi_handler    = midi_handler
        self.chord_detector  = chord_detector
        self.gamepad_handler = gamepad_handler
        self.preset_manager  = preset_manager

        # Set after audio engine subprocess starts (polled by loading screen)
        self.synth_engine = None

        self._surface: pygame.Surface | None = None
        self._clock: pygame.time.Clock | None = None
        self._fb0_writer: Fb0Writer | None = None
        self._running = False

        # Screen cache: lazy-instantiated, state persists across visits
        self._screen_cache: dict = {}
        self._current_screen = None

    # ── Startup ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Initialize Pygame, start audio engine, and enter the main loop."""
        self._init_pygame()
        theme.init_fonts()
        self._register_global_gamepad()
        self._running = True

        # Start engine in background; loading screen polls is_available()
        self._start_engine_async()

        # Show loading screen until engine is ready (has its own mini-loop)
        self._run_loading_screen()

        if self._running:
            self.goto("main_menu")
            self._main_loop()

        if self._fb0_writer is not None:
            self._fb0_writer.close()
        pygame.quit()

    def _init_pygame(self) -> None:
        """Initialize Pygame in offscreen mode and open /dev/fb0 for output.

        SDL_VIDEODRIVER is forced to 'offscreen' so pygame.init() always
        succeeds regardless of the display environment (tty, SSH, HDMI).
        Each rendered frame is written directly to /dev/fb0 via Fb0Writer,
        which scales 480x320 to the fb0 native size (790x600 on OStra) and
        writes raw BGRA bytes.  fbcp then mirrors fb0 to both the SPI TFT and
        HDMI output.  The double-scaling cancels perfectly so the image is
        pixel-accurate on both outputs.

        If /dev/fb0 is not writable (SSH, dev machine) Fb0Writer silently
        degrades to a no-op, allowing headless testing without changes.
        """
        # Force offscreen: works on tty, over SSH, and in CI without X11.
        os.environ["SDL_VIDEODRIVER"] = "offscreen"
        os.environ.setdefault("SDL_FBDEV",   "/dev/fb0")
        os.environ.setdefault("SDL_FBACCEL", "0")

        pygame.init()
        # Offscreen surface - rendered frames go to fb0 via Fb0Writer, not SDL.
        self._surface = pygame.display.set_mode(
            (theme.SCREEN_W, theme.SCREEN_H), pygame.NOFRAME
        )
        print("[arm_ui] pygame init OK (driver: offscreen + fb0_writer)", file=sys.stderr)

        self._fb0_writer = Fb0Writer(theme.SCREEN_W, theme.SCREEN_H)

        self._clock = pygame.time.Clock()
        pygame.mouse.set_visible(False)

    def _register_global_gamepad(self) -> None:
        """Register app-level gamepad shortcuts that survive screen changes."""
        gp = self.gamepad_handler
        gp.set_global_button_callback(GP.START, lambda: self.goto("main_menu"))
        gp.set_global_combo_callback(
            (GP.LB, GP.RB),
            lambda: self.synth_engine.all_notes_off() if self.synth_engine else None,
        )

    def _start_engine_async(self) -> None:
        """Start the SynthEngineProxy subprocess in a background thread.

        The main thread polls self.synth_engine.is_available() via the loading
        screen. Assigning self.synth_engine is a single atomic reference write
        (safe under CPython GIL).
        """
        def _start():
            from music.engine_proxy import SynthEngineProxy
            device_index = self.config_manager.get_audio_device_index()
            # Sentinel -2 = system default (None to engine), -1 = no audio
            actual_index = None if device_index in (-2, None) else device_index
            buffer_size  = self.config_manager.get_buffer_size()
            audio_backend = self.config_manager.get_audio_backend()
            proxy = SynthEngineProxy(
                output_device_index=actual_index,
                buffer_size=buffer_size,
                audio_backend=audio_backend,
            )
            self.synth_engine = proxy
            # Open MIDI device once proxy object exists
            selected = self.device_manager.get_selected_device()
            if selected:
                try:
                    self.midi_handler.open_device(selected)
                except Exception as exc:
                    print(f"[arm_ui] MIDI open failed: {exc}", file=sys.stderr)

        t = threading.Thread(target=_start, daemon=True, name="arm-engine-start")
        t.start()

    def _run_loading_screen(self) -> None:
        """Run a dedicated loop for the loading screen (before main loop starts)."""
        from arm_ui.screens.loading import LoadingScreen

        loading = LoadingScreen(self)
        loading.on_enter()

        while self._running and not loading._transitioned:
            dt = self._clock.tick(self.FPS) / 1000.0
            self.gamepad_handler.poll()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                    return

            loading.update(dt)
            loading.draw(self._surface)
            self._fb0_writer.write_surface(self._surface)

        loading.on_exit()

    # ── Main loop ────────────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        """Primary event + render loop."""
        while self._running:
            dt = self._clock.tick(self.FPS) / 1000.0

            self.gamepad_handler.poll()
            self.midi_handler.poll_messages()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif self._current_screen is not None:
                    self._current_screen.handle_event(event)

            if self._current_screen is not None:
                self._current_screen.update(dt)
                self._current_screen.draw(self._surface)

            self._fb0_writer.write_surface(self._surface)

    # ── Screen management ────────────────────────────────────────────────────

    def goto(self, screen_name: str, **kwargs) -> None:
        """Transition to a named screen.

        Clears gamepad callbacks and calls on_exit() on the current screen before
        activating the new one. Screens are lazy-created and cached so state
        (e.g. scroll position, last preset index) persists across visits.
        """
        if self._current_screen is not None:
            self.gamepad_handler.clear_callbacks()
            self._current_screen.on_exit()

        if self.synth_engine is not None:
            self.synth_engine.soft_all_notes_off()

        if screen_name not in self._screen_cache:
            self._screen_cache[screen_name] = self._create_screen(screen_name)

        self._current_screen = self._screen_cache[screen_name]
        self._current_screen.on_enter(**kwargs)

    def _create_screen(self, name: str):
        # Each import is deferred inside its lambda so missing modules only fail
        # when that specific screen is first requested, not at app startup.
        def _main_menu():
            from arm_ui.screens.main_menu import MainMenuScreen
            return MainMenuScreen(self)

        def _synth():
            from arm_ui.screens.synth import SynthScreen
            return SynthScreen(self)

        def _stub(title):
            from arm_ui.screens.stub import StubScreen
            return StubScreen(self, title)

        mapping = {
            "main_menu":  _main_menu,
            "synth":      _synth,
            "piano":      lambda: _stub("Piano"),
            "metronome":  lambda: _stub("Metronome"),
            "tambor":     lambda: _stub("Tambor"),
            "compendium": lambda: _stub("Compendium"),
            "config":     lambda: _stub("Config"),
        }
        factory = mapping.get(name)
        if factory is None:
            raise ValueError(f"Unknown screen name: {name!r}")
        return factory()

    def quit(self) -> None:
        """Cleanly stop the application."""
        self._running = False
