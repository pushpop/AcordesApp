from textual.widgets import Static, Label
from textual.containers import Vertical
from textual.binding import Binding
from components.header_widget import HeaderWidget
import pygame
import numpy as np

class MetronomeMode(Vertical):
    """A metronome mode for the application."""

    DEFAULT_CSS = """
    MetronomeMode:focus {
        border: heavy $accent;
    }
    MetronomeMode {
        align: center middle;
        padding: 1;
    }
    #metronome-display {
        width: 100%;
        height: 7;
        align: center middle;
        text-align: center;
    }
    #tempo-mark-label {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    #metronome-info {
        padding-top: 1;
        width: 100%;
        align: center middle;
    }
    #info-display {
        width: auto;
        height: auto;
    }
    #shortcuts-label {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("p", "toggle_metronome", "Start/Stop", show=False),
        Binding("space", "toggle_metronome", "Start/Stop", show=False),
        Binding("up", "increase_tempo", "Tempo +", show=False),
        Binding("down", "decrease_tempo", "Tempo -", show=False),
        Binding("left", "decrease_time_signature", "Time Sig -", show=False),
        Binding("right", "increase_time_signature", "Time Sig +", show=False),
    ]
    
    can_focus = True

    MIN_BPM = 50
    MAX_BPM = 300

    COMMON_TIME_SIGNATURES = [
        (2, 4), (3, 4), (4, 4),  # Simple
        (2, 2),                  # Cut Time
        (6, 8), (9, 8), (12, 8)  # Compound
    ]
    ACCENT_PATTERNS = {
        (2, 4): [1, 0],
        (3, 4): [1, 0, 0],
        (4, 4): [1, 0, 0, 0],
        (2, 2): [1, 0],
        (6, 8): [1, 0, 0, 1, 0, 0],
        (9, 8): [1, 0, 0, 1, 0, 0, 1, 0, 0],
        (12, 8): [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0],
    }

    TEMPO_MARKS = [
        (40, "Grave"), (50, "Largo"), (60, "Lento"), (70, "Adagio"),
        (80, "Andante"), (108, "Moderato"), (120, "Allegretto"),
        (156, "Allegro"), (176, "Vivace"), (200, "Presto"), (999, "Prestissimo")
    ]

    def _get_tempo_marking(self) -> str:
        """Get the Italian tempo marking for the current BPM."""
        for max_bpm, name in self.TEMPO_MARKS:
            if self.tempo <= max_bpm:
                return name
        return ""

    ASCII_NUMBERS = {
        '0': ["███","█ █","█ █","█ █","███"],
        '1': [" █ ","██ "," █ "," █ ","███"],
        '2': ["███","  █","███","█  ","███"],
        '3': ["███","  █","███","  █","███"],
        '4': ["█ █","█ █","███","  █","  █"],
        '5': ["███","█  ","███","  █","███"],
        '6': ["███","█  ","███","█ █","███"],
        '7': ["███","  █","  █","  █","  █"],
        '8': ["███","█ █","███","█ █","███"],
        '9': ["███","█ █","███","  █","███"],
        '/': ["  █"," █ "," █ "," █ ","█  "],
    }

    def _generate_ascii_art(self, text: str) -> str:
        """Generates multi-line ASCII art for a given string."""
        lines = [""] * 5
        for char in text:
            if char in self.ASCII_NUMBERS:
                for i, line in enumerate(self.ASCII_NUMBERS[char]):
                    lines[i] += line + " "
        return "\n".join(lines)

    def _generate_combined_art(self) -> str:
        """Generates and combines the ASCII art for tempo and time signature."""
        tempo_str = str(self.tempo)
        time_sig_str = f"{self.time_signature[0]}/{self.time_signature[1]}"
        spacer = "     "

        tempo_lines = self._generate_ascii_art(tempo_str).split('\n')
        time_sig_lines = self._generate_ascii_art(time_sig_str).split('\n')

        combined_lines = []
        for i in range(len(tempo_lines)):
            combined_lines.append(tempo_lines[i] + spacer + time_sig_lines[i])
        
        return "\n".join(combined_lines)

    def __init__(self, config_manager=None):
        super().__init__()
        self.config_manager = config_manager
        self.tempo = config_manager.get_bpm() if config_manager else 120
        try:
            self.time_signature_index = self.COMMON_TIME_SIGNATURES.index((4, 4))
        except ValueError:
            self.time_signature_index = 2
        
        self.time_signature = self.COMMON_TIME_SIGNATURES[self.time_signature_index]
        self._is_running = False
        self.beat_counter = 0
        self.timer = None

        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        sample_rate = pygame.mixer.get_init()[0]

        def generate_click(freq, duration_ms):
            duration_s = duration_ms / 1000.0
            num_samples = int(sample_rate * duration_s)
            t = np.linspace(0, duration_s, num_samples, False)
            audio_data = np.sin(2 * np.pi * freq * t)
            decay = np.exp(-t / 0.01)
            audio_data *= decay
            audio_data = (audio_data * 32767).astype(np.int16)
            stereo_data = np.zeros((num_samples, 2), dtype=np.int16)
            stereo_data[:, 0] = audio_data
            stereo_data[:, 1] = audio_data
            return pygame.sndarray.make_sound(stereo_data)

        self.accent_beat_sound = generate_click(1200, 50)
        self.beat_sound = generate_click(880, 50)

    def _generate_beat_bar_art(self, current_beat: int) -> str:
        total_beats = self.time_signature[0]
        off_block = ["╭─────╮", "│     │", "│     │", "│     │", "╰─────╯"]
        on_block = ["╭─────╮", "│█████│", "│█████│", "│█████│", "╰─────╯"]
        output_lines = [""] * 5
        for i in range(total_beats):
            block_to_use = on_block if i == current_beat else off_block
            for line_num in range(5):
                output_lines[line_num] += block_to_use[line_num] + " "
        return "\n".join(output_lines)
        
    def on_mount(self):
        self.focus()

    def compose(self):
        yield HeaderWidget(title="METRONOME", subtitle="Keep the rhythm")
        yield Static(self._generate_beat_bar_art(-1), id="metronome-display")
        yield Label(self._get_tempo_marking(), id="tempo-mark-label")
        combined_art = self._generate_combined_art()
        with Vertical(id="metronome-info"):
            yield Static(combined_art, id="info-display")

    def _update_metronome(self):
        display = self.query_one("#metronome-display")
        beats_in_measure = self.time_signature[0]
        current_beat_in_measure = self.beat_counter % beats_in_measure
        display.update(self._generate_beat_bar_art(current_beat_in_measure))
        pattern = self.ACCENT_PATTERNS.get(self.time_signature, [1] + [0] * (beats_in_measure - 1))
        is_accented_beat = pattern[current_beat_in_measure] == 1
        if is_accented_beat:
            self.accent_beat_sound.play()
        else:
            self.beat_sound.play()
        self.beat_counter += 1

    def action_toggle_metronome(self):
        self._is_running = not self._is_running
        if self._is_running:
            self.beat_counter = 0
            interval = 60.0 / self.tempo
            self.timer = self.set_interval(interval, self._update_metronome)
            self._update_metronome()
        else:
            if self.timer:
                self.timer.stop()
            self.query_one("#metronome-display").update(self._generate_beat_bar_art(-1))

    def _update_timer(self):
        if self._is_running:
            if self.timer:
                self.timer.stop()
            interval = 60.0 / self.tempo
            self.timer = self.set_interval(interval, self._update_metronome)

    def action_increase_tempo(self):
        self.tempo = min(self.MAX_BPM, self.tempo + 1)
        if self.config_manager:
            self.config_manager.set_bpm(self.tempo)
        self.query_one("#info-display").update(self._generate_combined_art())
        self.query_one("#tempo-mark-label").update(self._get_tempo_marking())
        self._update_timer()

    def action_decrease_tempo(self):
        self.tempo = max(self.MIN_BPM, self.tempo - 1)
        if self.config_manager:
            self.config_manager.set_bpm(self.tempo)
        self.query_one("#info-display").update(self._generate_combined_art())
        self.query_one("#tempo-mark-label").update(self._get_tempo_marking())
        self._update_timer()

    def action_increase_time_signature(self):
        self.time_signature_index = (self.time_signature_index + 1) % len(self.COMMON_TIME_SIGNATURES)
        self.time_signature = self.COMMON_TIME_SIGNATURES[self.time_signature_index]
        self.query_one("#info-display").update(self._generate_combined_art())
        if not self._is_running:
            self.query_one("#metronome-display").update(self._generate_beat_bar_art(-1))

    def action_decrease_time_signature(self):
        self.time_signature_index = (self.time_signature_index - 1 + len(self.COMMON_TIME_SIGNATURES)) % len(self.COMMON_TIME_SIGNATURES)
        self.time_signature = self.COMMON_TIME_SIGNATURES[self.time_signature_index]
        self.query_one("#info-display").update(self._generate_combined_art())
        if not self._is_running:
            self.query_one("#metronome-display").update(self._generate_beat_bar_art(-1))

    def on_unmount(self):
        if self.timer:
            self.timer.stop()
