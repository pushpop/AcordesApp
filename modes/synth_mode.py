"""Synth mode - Monophonic synthesizer interface."""
from textual.widget import Widget
from textual.containers import Container, Vertical, Horizontal, Center, ScrollableContainer, VerticalScroll, Grid
from textual.widgets import Static, Label
from textual.binding import Binding
from typing import TYPE_CHECKING, Set, Optional

from music.synth_engine import SynthEngine

if TYPE_CHECKING:
    from midi.input_handler import MIDIInputHandler


class SynthMode(Widget):
    """Widget for monophonic synthesizer interface."""

    # Make widget focusable to receive key events
    can_focus = True

    BINDINGS = [
        Binding("w", "toggle_waveform", "Waveform", show=False),
        Binding("s", "adjust_octave('up')", "Oct+", show=False),
        Binding("x", "adjust_octave('down')", "Oct-", show=False),
        Binding("up", "adjust_volume('up')", "Vol+", show=False),
        Binding("down", "adjust_volume('down')", "Vol-", show=False),
        Binding("left", "adjust_cutoff('left')", "Cut-", show=False),
        Binding("right", "adjust_cutoff('right')", "Cut+", show=False),
        Binding("q", "adjust_resonance('up')", "Res+", show=False),
        Binding("a", "adjust_resonance('down')", "Res-", show=False),
        Binding("e", "adjust_attack('up')", "Atk+", show=False),
        Binding("d", "adjust_attack('down')", "Atk-", show=False),
        Binding("r", "adjust_decay('up')", "Dec+", show=False),
        Binding("f", "adjust_decay('down')", "Dec-", show=False),
        Binding("t", "adjust_sustain('up')", "Sus+", show=False),
        Binding("g", "adjust_sustain('down')", "Sus-", show=False),
        Binding("y", "adjust_release('up')", "Rel+", show=False),
        Binding("h", "adjust_release('down')", "Rel-", show=False),
        Binding("u", "adjust_intensity('up')", "Int+", show=False),
        Binding("j", "adjust_intensity('down')", "Int-", show=False),
        Binding("space", "panic", "Panic (All Notes Off)", show=False),
    ]

    CSS = """
    SynthMode {
        width: 100%;
        height: 100%;
        layout: vertical;
        padding: 0;
        margin: 0;
        align: center top;
    }

    #title {
        width: 100%;
        height: auto;
        text-align: center;
        color: #00ff00;
    }

    #status {
        width: 100%;
        height: auto;
        text-align: center;
        padding: 0;
        color: #666666;
        text-style: italic;
    }

    #synth-container {
        layout: horizontal;
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }

    /* Footer section - fixed at bottom */
    #controls-help {
        width: 100%;
        height: auto;
        background: #1a1a1a;
        border-top: heavy #00ff00;
        padding: 0;
        margin: 0;
        text-align: center;
        content-align: center middle;
    }

    /* Individual synth parameter boxes */
    #oscillator-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #1a1a1a;
        padding: 0;
        margin: 0;
    }

    #filter-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #1a1a1a;
        padding: 0;
        margin: 0;
    }

    #envelope-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #1a1a1a;
        padding: 0;
        margin: 0;
    }

    #mixer-section {
        layout: vertical;
        width: 1fr;
        height: auto;
        background: #1a1a1a;
        padding: 0;
        margin: 0;
    }

    .section-label {
        color: #00ff00;
        text-style: bold;
        padding: 0;
        margin: 0;
        width: 100%;
        height: 1;
        text-align: left;
    }

    .control-container {
        layout: vertical;
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }

    .box-spacer {
        height: 1;
        width: 100%;
        margin: 0;
        padding: 0;
    }

    .control-label {
        color: #888888;
        width: 100%;
        height: 1;
        text-align: left;
        padding: 0;
        margin: 0;
    }

    .control-value {
        color: #ffffff;
        text-style: bold;
        width: 100%;
        height: auto;
        text-align: left;
        padding: 0;
        margin: 0;
    }

    .waveform-button {
        color: #666666;
        padding: 0 1;
    }

    .waveform-button-active {
        color: #00ff00;
        text-style: bold reverse;
        padding: 0 1;
    }
    """

    def __init__(self, midi_handler: 'MIDIInputHandler'):
        super().__init__()
        self.midi_handler = midi_handler

        # Initialize synth engine
        self.synth_engine = SynthEngine()

        # Synth parameters with musical ranges
        self.waveform = "sine"  # sine, square, sawtooth, triangle
        self.octave = 0  # -2 to +2 (octave transpose)
        self.amp_level = 0.75  # 0.0 to 1.0 (master amplitude)
        self.cutoff = 2000.0  # 20Hz to 20000Hz
        self.resonance = 0.3  # 0.0 to 0.9 (avoid self-oscillation at 1.0)
        self.attack = 0.01  # 0.001s to 5.0s
        self.decay = 0.2  # 0.001s to 5.0s
        self.sustain = 0.7  # 0.0 to 1.0
        self.release = 0.05  # 0.001s to 5.0s
        self.intensity = 0.8  # 0.0 to 1.0

        # Current note being played (monophonic)
        self.current_note: Optional[int] = None

        # References to display widgets
        self.waveform_display = None
        self.octave_display = None
        self.amp_display = None
        self.cutoff_display = None
        self.resonance_display = None
        self.attack_display = None
        self.decay_display = None
        self.sustain_display = None
        self.release_display = None
        self.intensity_display = None
        self.status_display = None

    def compose(self):
        """Compose the synth mode layout."""
        # Title and status at top - centered
        with Center():
            yield Label(self._get_synth_ascii(), id="title")
        with Center():
            self.status_display = Label(self._get_status_text(), id="status")
            yield self.status_display

        # One line spacing before synth controls
        yield Label("")

        # Synth controls container
        with Horizontal(id="synth-container"):
                # Oscillator section
                with Vertical(id="oscillator-section"):
                    yield Label(self._create_section_box("OSCILLATOR"), classes="section-label")
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("Wave [W]"), classes="control-label")
                    self.waveform_display = Label(
                        self._format_waveform_display(),
                        classes="control-value",
                        id="waveform-display"
                    )
                    yield self.waveform_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("Oct [S/X]"), classes="control-label")
                    self.octave_display = Label(
                        self._format_octave_display(),
                        classes="control-value",
                        id="octave-display"
                    )
                    yield self.octave_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_section_box_bottom(), classes="section-label")

                # Filter section
                with Vertical(id="filter-section"):
                    yield Label(self._create_section_box("FILTER"), classes="section-label")
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("Cut [←/→]"), classes="control-label")
                    import math
                    log_cutoff = math.log10(self.cutoff)
                    log_min = math.log10(20.0)
                    log_max = math.log10(20000.0)
                    normalized = (log_cutoff - log_min) / (log_max - log_min)
                    freq_str = f"{int(self.cutoff)}Hz"
                    self.cutoff_display = Label(
                        self._format_slider_with_value(normalized, 0.0, 1.0, freq_str),
                        classes="control-value",
                        id="cutoff-display"
                    )
                    yield self.cutoff_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("Res [Q/A]"), classes="control-label")
                    self.resonance_display = Label(
                        self._format_slider_with_value(self.resonance / 0.9, 0.0, 1.0, f"{int(self.resonance * 100)}%"),
                        classes="control-value",
                        id="resonance-display"
                    )
                    yield self.resonance_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_section_box_bottom(), classes="section-label")

                # Envelope section (ADSR)
                with Vertical(id="envelope-section"):
                    yield Label(self._create_section_box("ENVELOPE"), classes="section-label")
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("A [E/D]"), classes="control-label")
                    self.attack_display = Label(
                        self._format_time_param(self.attack),
                        classes="control-value",
                        id="attack-display"
                    )
                    yield self.attack_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("D [R/F]"), classes="control-label")
                    self.decay_display = Label(
                        self._format_time_param(self.decay),
                        classes="control-value",
                        id="decay-display"
                    )
                    yield self.decay_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("S [T/G]"), classes="control-label")
                    self.sustain_display = Label(
                        self._format_slider_with_value(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%"),
                        classes="control-value",
                        id="sustain-display"
                    )
                    yield self.sustain_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("R [Y/H]"), classes="control-label")
                    self.release_display = Label(
                        self._format_time_param(self.release),
                        classes="control-value",
                        id="release-display"
                    )
                    yield self.release_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("Int [U/J]"), classes="control-label")
                    self.intensity_display = Label(
                        self._format_slider_with_value(self.intensity, 0.0, 1.0, f"{int(self.intensity * 100)}%"),
                        classes="control-value",
                        id="intensity-display"
                    )
                    yield self.intensity_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_section_box_bottom(), classes="section-label")

                # AMP section
                with Vertical(id="mixer-section"):
                    yield Label(self._create_section_box("AMP"), classes="section-label")
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_box_line("Amp [↑/↓]"), classes="control-label")
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    self.amp_display = Label(
                        self._format_slider_with_value(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%"),
                        classes="control-value",
                        id="amp-display"
                    )
                    yield self.amp_display
                    yield Label(self._create_empty_box_line(), classes="section-label")
                    yield Label(self._create_section_box_bottom(), classes="section-label")

        # Controls help section (Grid row 2: 1fr - fills remaining space)
        yield Static("[bold #00ff00]CONTROLS:[/] [W] Wave [S/X] Oct [↑/↓] Amp [←/→] Cut [Q/A] Res [E/D] Atk [R/F] Dec [T/G] Sus [Y/H] Rel [U/J] Int [SPACE] Panic", id="controls-help")

    def on_mount(self):
        """Called when screen is mounted."""
        # Set widget focus to receive keyboard events
        self.focus()

        # Set up MIDI callbacks
        self.midi_handler.set_callbacks(
            note_on=self._on_note_on,
            note_off=self._on_note_off,
            pitch_bend=self._on_pitch_bend,
            control_change=self._on_control_change
        )

        # Start polling for MIDI messages
        self.set_interval(0.01, self._poll_midi)

        # Update synth engine with initial parameters
        self.synth_engine.update_parameters(
            waveform=self.waveform,
            octave=self.octave,
            amp_level=self.amp_level,
            cutoff=self.cutoff,
            resonance=self.resonance,
            attack=self.attack,
            decay=self.decay,
            sustain=self.sustain,
            release=self.release,
            intensity=self.intensity
        )

    def on_unmount(self):
        """Clean up when widget is removed."""
        self.synth_engine.close()

    def _poll_midi(self):
        """Poll for MIDI messages."""
        if self.midi_handler.is_device_open():
            self.midi_handler.poll_messages()

    def _on_note_on(self, note: int, velocity: int):
        """Callback for MIDI note on events with velocity."""
        self.current_note = note
        self.synth_engine.note_on(note, velocity)

        # Update status display with velocity
        if self.status_display:
            note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            octave = (note // 12) - 1
            note_name = note_names[note % 12]
            self.status_display.update(f"🎵 Playing: {note_name}{octave} (MIDI {note}) • Vel: {velocity}")

    def _on_note_off(self, note: int):
        """Callback for MIDI note off events."""
        # Always send note_off to the synth engine (polyphonic)
        self.synth_engine.note_off(note)

        # Update current_note tracking (only for display purposes)
        if self.current_note == note:
            self.current_note = None

            # Update status display
            if self.status_display:
                self.status_display.update(self._get_status_text())

    def _on_pitch_bend(self, value: int):
        """Callback for MIDI pitch bend events."""
        self.synth_engine.pitch_bend_change(value)

    def _on_control_change(self, controller: int, value: int):
        """Callback for MIDI control change events."""
        # Handle modulation wheel (CC1)
        if controller == 1:
            self.synth_engine.modulation_change(value)

    def _get_status_text(self) -> str:
        """Get status text."""
        if self.synth_engine.is_available():
            if self.midi_handler.is_device_open():
                return "🎵 Synth ready - Play some notes!"
            else:
                return "⚠ No MIDI device connected - Select one in Config Mode"
        else:
            return "⚠ Audio not available (install pyaudio: pip install pyaudio)"

    def _get_synth_ascii(self) -> str:
        """Get the SYNTH ASCII art in compact style."""
        return "╔───────────────────────────────────────────────╗\n│          S Y N T H   M O D E                  │\n╚───────────────────────────────────────────────╝"

    def _create_section_box(self, title: str, width: int = 28) -> str:
        """Create a box header with title."""
        # Center the title
        title_padded = f" {title} "
        padding = width - len(title_padded) - 2  # -2 for the corner characters
        left_pad = padding // 2
        right_pad = padding - left_pad

        # Create top border with title using ─ for horizontal lines
        top_line = f"╔{'─' * left_pad}{title_padded}{'─' * right_pad}╗"

        return f"[bold #00ff00]{top_line}[/]"

    def _create_section_box_bottom(self, width: int = 28) -> str:
        """Create a box bottom border."""
        # width - 2 to account for the corner characters (╚ and ╝)
        bottom_line = f"╚{'─' * (width - 2)}╝"
        return f"[bold #00ff00]{bottom_line}[/]"

    def _create_box_line(self, content: str, width: int = 28) -> str:
        """Create a single line within a box with proper padding."""
        # Remove existing borders if any
        content = content.replace("│", "").strip()
        # Calculate padding to reach width (accounting for 2 border chars)
        inner_width = width - 2
        if len(content) > inner_width:
            content = content[:inner_width]
        padding = inner_width - len(content)
        left_pad = padding // 2
        right_pad = padding - left_pad
        return f"[#00ff00]│{' ' * left_pad}{content}{' ' * right_pad}│[/]"

    def _create_empty_box_line(self, width: int = 28) -> str:
        """Create an empty line within a box."""
        inner_width = width - 2
        return f"[#00ff00]│{' ' * inner_width}│[/]"

    def _create_slider(self, value: float, min_val: float, max_val: float, width: int = 26) -> str:
        """Create a visual slider representation."""
        # Normalize value to 0-1 range
        normalized = (value - min_val) / (max_val - min_val)
        filled = int(normalized * width)
        empty = width - filled

        # Create slider with filled and empty sections - ensure exact width
        slider_content = "█" * filled + "░" * empty
        # Apply colors: green for filled, dark gray for empty
        if filled > 0 and empty > 0:
            slider = "[#00ff00]" + "█" * filled + "[/][#333333]" + "░" * empty + "[/]"
        elif filled == width:
            slider = "[#00ff00]" + "█" * filled + "[/]"
        else:  # empty == width
            slider = "[#333333]" + "░" * empty + "[/]"
        return slider

    def _format_time_param(self, time_value: float) -> str:
        """Format time parameter with logarithmic slider and nice time display."""
        import math

        # Logarithmic display mapping (1ms to 5s)
        log_time = math.log10(time_value)
        log_min = math.log10(0.001)
        log_max = math.log10(5.0)
        normalized = (log_time - log_min) / (log_max - log_min)

        # Format time nicely
        if time_value < 0.01:
            time_str = f"{time_value*1000:.0f}ms"
        else:
            time_str = f"{time_value:.2f}s"

        # Add side borders with centered time string
        slider = self._create_slider(normalized, 0.0, 1.0)
        total_width = 26
        padding = total_width - len(time_str)
        left_pad = padding // 2
        right_pad = padding - left_pad
        time_padded = " " * left_pad + time_str + " " * right_pad
        # Build complete lines with borders
        line1 = f"[#00ff00]│{slider}│[/]"
        line2 = f"[#00ff00]│{time_padded}│[/]"
        return f"{line1}\n{line2}"

    def _format_slider_with_value(self, value: float, min_val: float, max_val: float, value_str: str) -> str:
        """Format slider with value display and side borders."""
        slider = self._create_slider(value, min_val, max_val)
        # Center the value string (26 chars slider + padding)
        total_width = 26
        padding = total_width - len(value_str)
        left_pad = padding // 2
        right_pad = padding - left_pad
        value_padded = " " * left_pad + value_str + " " * right_pad
        # Build complete lines with borders
        line1 = f"[#00ff00]│{slider}│[/]"
        line2 = f"[#00ff00]│{value_padded}│[/]"
        return f"{line1}\n{line2}"

    def _get_waveform_display(self) -> str:
        """Get waveform display with current selection highlighted."""
        if self.waveform == "sine":
            sine_text = "[bold reverse]SIN[/]"
        else:
            sine_text = "SIN"

        if self.waveform == "square":
            square_text = "[bold reverse]SQR[/]"
        else:
            square_text = "SQR"

        if self.waveform == "sawtooth":
            saw_text = "[bold reverse]SAW[/]"
        else:
            saw_text = "SAW"

        if self.waveform == "triangle":
            triangle_text = "[bold reverse]TRI[/]"
        else:
            triangle_text = "TRI"

        return f"{sine_text}  {square_text}  {saw_text}  {triangle_text}"

    def _format_waveform_display(self) -> str:
        """Format waveform display with side borders."""
        waveform_line = self._get_waveform_display()
        # Pad to exactly 26 chars to match box inner width
        # Remove Rich markup to get actual text length
        import re
        plain_text = re.sub(r'\[.*?\]', '', waveform_line)
        total_width = 26
        padding = total_width - len(plain_text)
        left_pad = padding // 2
        right_pad = padding - left_pad
        padded_line = " " * left_pad + waveform_line + " " * right_pad
        return f"[#00ff00]│{padded_line}│[/]"

    def _get_octave_display(self) -> str:
        """Get octave display with organ feet notation."""
        # Map octave to organ feet notation
        feet_map = {
            -2: "32'",  # Two octaves down
            -1: "16'",  # One octave down
            0: "8'",    # Standard pitch
            1: "4'",    # One octave up
            2: "2'",    # Two octaves up
        }
        feet = feet_map.get(self.octave, "8'")

        # Create visual indicator showing octave position
        # -2  -1   0  +1  +2
        #  ●   ○   ○   ○   ○
        octave_positions = [-2, -1, 0, 1, 2]
        indicators = []
        for pos in octave_positions:
            if pos == self.octave:
                indicators.append("●")  # Filled dot for current octave
            else:
                indicators.append("○")  # Empty dot for other positions

        visual = " ".join(indicators)
        return f"{visual}\n{feet} ({self.octave:+d})"

    def _format_octave_display(self) -> str:
        """Format octave display with side borders."""
        lines = self._get_octave_display().split('\n')
        formatted = []
        total_width = 26  # Match box inner width
        for line in lines:
            # Pad each line to exactly 26 chars
            padding = total_width - len(line)
            left_pad = padding // 2
            right_pad = padding - left_pad
            padded_line = " " * left_pad + line + " " * right_pad
            formatted.append(f"[#00ff00]│{padded_line}│[/]")
        return '\n'.join(formatted)

    # Action methods for keyboard controls
    def action_toggle_waveform(self):
        """Toggle between waveforms: sine -> square -> sawtooth -> triangle -> sine."""
        if self.waveform == "sine":
            self.waveform = "square"
        elif self.waveform == "square":
            self.waveform = "sawtooth"
        elif self.waveform == "sawtooth":
            self.waveform = "triangle"
        else:
            self.waveform = "sine"

        self.synth_engine.update_parameters(waveform=self.waveform)

        if self.waveform_display:
            self.waveform_display.update(self._format_waveform_display())

    def action_adjust_octave(self, direction: str = "up"):
        """Adjust oscillator octave transpose (like organ feet: 32', 16', 8', 4', 2')."""
        if direction == "up":
            self.octave = min(2, self.octave + 1)  # Max +2 octaves
        else:
            self.octave = max(-2, self.octave - 1)  # Max -2 octaves

        self.synth_engine.update_parameters(octave=self.octave)

        if self.octave_display:
            self.octave_display.update(self._format_octave_display())

    def action_adjust_volume(self, direction: str = "up"):
        """Adjust AMP level up or down."""
        if direction == "up":
            self.amp_level = min(1.0, self.amp_level + 0.05)
        else:
            self.amp_level = max(0.0, self.amp_level - 0.05)

        self.synth_engine.update_parameters(amp_level=self.amp_level)

        if self.amp_display:
            self.amp_display.update(
                self._format_slider_with_value(self.amp_level, 0.0, 1.0, f"{int(self.amp_level * 100)}%")
            )

    def action_adjust_cutoff(self, direction: str = "right"):
        """Adjust filter cutoff frequency (logarithmic for musical perception)."""
        import math

        if direction == "right":
            # Logarithmic increase feels more musical
            self.cutoff = min(20000.0, self.cutoff * 1.1)
        else:
            # Logarithmic decrease
            self.cutoff = max(20.0, self.cutoff / 1.1)

        self.synth_engine.update_parameters(cutoff=self.cutoff)

        if self.cutoff_display:
            # Display on log scale for better visualization
            log_cutoff = math.log10(self.cutoff)
            log_min = math.log10(20.0)
            log_max = math.log10(20000.0)
            normalized = (log_cutoff - log_min) / (log_max - log_min)

            # Format frequency display nicely
            if self.cutoff >= 1000:
                freq_str = f"{self.cutoff/1000:.1f}kHz"
            else:
                freq_str = f"{int(self.cutoff)}Hz"

            self.cutoff_display.update(
                self._format_slider_with_value(normalized, 0.0, 1.0, freq_str)
            )

    def action_adjust_resonance(self, direction: str = "up"):
        """Adjust filter resonance (0-90% to avoid self-oscillation)."""
        if direction == "up":
            # Limit to 0.9 to avoid self-oscillation
            self.resonance = min(0.9, self.resonance + 0.05)
        else:
            self.resonance = max(0.0, self.resonance - 0.05)

        self.synth_engine.update_parameters(resonance=self.resonance)

        if self.resonance_display:
            # Show as percentage for clarity
            self.resonance_display.update(
                self._format_slider_with_value(self.resonance / 0.9, 0.0, 1.0, f"{int(self.resonance * 100)}%")
            )

    def action_adjust_attack(self, direction: str = "up"):
        """Adjust envelope attack time (1ms to 5s, exponential)."""
        if direction == "up":
            # Exponential increase for fine control at short times
            self.attack = min(5.0, self.attack * 1.15)
        else:
            # Exponential decrease
            self.attack = max(0.001, self.attack / 1.15)

        self.synth_engine.update_parameters(attack=self.attack)

        if self.attack_display:
            self.attack_display.update(self._format_time_param(self.attack))

    def action_adjust_decay(self, direction: str = "up"):
        """Adjust envelope decay time (1ms to 5s, exponential)."""
        if direction == "up":
            # Exponential increase for fine control at short times
            self.decay = min(5.0, self.decay * 1.15)
        else:
            # Exponential decrease
            self.decay = max(0.001, self.decay / 1.15)

        self.synth_engine.update_parameters(decay=self.decay)

        if self.decay_display:
            self.decay_display.update(self._format_time_param(self.decay))

    def action_adjust_sustain(self, direction: str = "up"):
        """Adjust envelope sustain level (0-100%)."""
        if direction == "up":
            self.sustain = min(1.0, self.sustain + 0.05)
        else:
            self.sustain = max(0.0, self.sustain - 0.05)

        self.synth_engine.update_parameters(sustain=self.sustain)

        if self.sustain_display:
            self.sustain_display.update(
                self._format_slider_with_value(self.sustain, 0.0, 1.0, f"{int(self.sustain * 100)}%")
            )

    def action_adjust_release(self, direction: str = "up"):
        """Adjust envelope release time (1ms to 5s, exponential)."""
        if direction == "up":
            # Exponential increase for fine control at short times
            self.release = min(5.0, self.release * 1.15)
        else:
            # Exponential decrease
            self.release = max(0.001, self.release / 1.15)

        self.synth_engine.update_parameters(release=self.release)

        if self.release_display:
            self.release_display.update(self._format_time_param(self.release))

    def action_adjust_intensity(self, direction: str = "up"):
        """Adjust envelope intensity (peak level, 0-100%)."""
        if direction == "up":
            self.intensity = min(1.0, self.intensity + 0.05)
        else:
            self.intensity = max(0.0, self.intensity - 0.05)

        self.synth_engine.update_parameters(intensity=self.intensity)

        if self.intensity_display:
            self.intensity_display.update(
                self._format_slider_with_value(self.intensity, 0.0, 1.0, f"{int(self.intensity * 100)}%")
            )

    def action_panic(self):
        """Emergency: Stop all playing notes immediately (MIDI panic)."""
        self.synth_engine.all_notes_off()
        self.app.notify("🛑 All notes off (Panic)", severity="warning", timeout=2)
