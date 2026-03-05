"""Synth preset manager — load, save, and cycle through presets."""
import json
import random
import re
from pathlib import Path
from typing import Optional

# Built-in preset filenames — always shown first, sorted alphabetically.
# Any file NOT in this set is treated as a user preset and appended in
# creation-time order (oldest → newest), so new saves always go to the end.
_BUILTIN_FILENAMES = {
    "bright_saw_lead.json",
    "church_organ.json",
    "deep_bass.json",
    "default.json",
    "glass_bells.json",
    "hollow_reed.json",
    "plucky_square.json",
    "soft_strings.json",
    "vintage_synth.json",
    "warm_pad.json",
}

# ──────────────────────────────────────────────────────────────
# Musical name word banks (English + European Portuguese)
# ──────────────────────────────────────────────────────────────
_ADJECTIVES = [
    # English
    "amber", "hollow", "dark", "bright", "warm", "deep", "soft", "ancient",
    "crystal", "misty", "golden", "broken", "silent", "wild", "lunar",
    "frozen", "sharp", "gentle", "distant", "heavy", "faded", "slow",
    "still", "raw", "open", "bare", "pale", "dense", "vast", "stark",
    # European Portuguese
    "escuro", "suave", "antigo", "dourado", "partido", "vazio", "nebuloso",
    "fundo", "sombrio", "brilhante", "calmo", "perdido", "eterno", "velado",
    "sereno", "profundo", "lento", "nublado", "fraco", "alto", "claro",
    # German
    "dunkel", "weich", "tief", "still", "fern", "rauh", "warm", "kalt",
    "leise", "sanft", "golden", "ewig", "breit", "hohl", "grau",
    "zart", "fremd", "weit", "alt", "leer",
    # French
    "sombre", "doux", "ancien", "doré", "brisé", "vide", "brumeux",
    "profond", "calme", "perdu", "éternel", "lent", "froid", "pur",
    "clair", "creux", "grave", "sourd", "vaste", "nu",
]

_NOUNS = [
    # English
    "reed", "fifth", "chord", "wave", "drift", "bell", "pulse", "pad",
    "string", "key", "echo", "tone", "veil", "dawn", "bloom",
    "harp", "bass", "fade", "crest", "flute", "mist", "arc", "void",
    "peak", "rift", "dust", "gleam", "shift", "fold", "grid",
    # European Portuguese
    "corda", "onda", "sino", "pulso", "acorde", "eco", "tom", "aurora",
    "ventos", "nevoa", "som", "bruma", "ritmo", "voz", "marcha",
    "sombra", "fio", "vazio", "cume", "luz",
    # German
    "klang", "welle", "saite", "glocke", "puls", "ton", "drift", "nebel",
    "stille", "chor", "bass", "raum", "stimme", "licht", "grenze",
    "tiefe", "schall", "hauch", "klang", "pfad",
    # French
    "corde", "onde", "cloche", "pulse", "accord", "écho", "voix", "aube",
    "brume", "son", "rythme", "marche", "voile", "sommet", "vide",
    "lueur", "seuil", "flux", "creux", "strie",
]

# Default parameter values — mirrors SynthEngine.__init__ defaults
DEFAULT_PARAMS: dict = {
    "waveform": "sine",
    "octave": 0,
    "noise_level": 0.0,
    "amp_level": 0.95,
    "cutoff": 2000.0,
    "hpf_cutoff": 20.0,
    "resonance": 0.3,
    "hpf_resonance": 0.0,
    "key_tracking": 0.5,
    "filter_mode": "ladder",  # kept for backward-compat with old presets; ignored by engine
    "attack": 0.01,
    "decay": 0.2,
    "sustain": 0.7,
    "release": 0.1,
    "intensity": 1.0,
    "rank2_enabled": False,
    "rank2_waveform": "sawtooth",
    "rank2_detune": 5.0,
    "rank2_mix": 0.5,
    "sine_mix": 0.0,
    "lfo_freq": 1.0,
    "lfo_vco_mod": 0.0,
    "lfo_vcf_mod": 0.0,
    "lfo_vca_mod": 0.0,
    # LFO extended — shape selector, per-target routing, master depth
    "lfo_shape":  "sine",   # "sine" | "triangle" | "square" | "sample_hold"
    "lfo_target": "all",    # "vco"  | "vcf"       | "vca"    | "all"
    "lfo_depth":  0.0,      # 0.0–1.0 master depth (scales mod to correct target)
    # FX Delay
    "delay_time":     0.25,  # seconds, 0.05–2.0
    "delay_feedback": 0.3,   # 0.0–0.9
    "delay_mix":      0.0,   # 0.0–1.0 wet/dry (0 = bypass)
    # Chorus
    "chorus_rate":   0.5,    # Hz, 0.1–10.0
    "chorus_depth":  0.0,    # 0.0–1.0 → 0–25ms sweep depth (0 = bypass)
    "chorus_mix":    0.0,    # 0.0–1.0 wet/dry (0 = bypass)
    "chorus_voices": 2,      # int 1–4 modulated taps
    # Arpeggiator (arp_bpm lives in config_manager, not in presets)
    "arp_enabled": False,
    "arp_mode":    "up",     # "up" | "down" | "up_down" | "random"
    "arp_gate":    0.5,      # 0.05–1.0 note-on fraction of step
    "arp_range":   1,        # 1–4 octave span
    # Voice Type
    "voice_type": "poly",    # "mono" | "poly" | "unison"
    # Filter EG — separate ADSR for filter cutoff modulation.
    # feg_amount=0.0 = completely bypassed (default); backward-compatible.
    # feg_amount range: -1.0 (full downward sweep) to +1.0 (full upward sweep).
    "feg_attack":  0.01,   # seconds, 0.001–4.0
    "feg_decay":   0.3,    # seconds, 0.001–4.0
    "feg_sustain": 0.0,    # 0.0–1.0 fraction of peak modulation held
    "feg_release": 0.3,    # seconds, 0.001–4.0
    "feg_amount":  0.0,    # -1.0–+1.0 modulation depth (0 = bypass)
}

PARAM_KEYS = list(DEFAULT_PARAMS.keys())


class Preset:
    """A single preset entry."""

    def __init__(self, name: str, filename: str, params: dict, origin: str = "user"):
        self.name = name
        self.filename = filename  # basename, e.g. "warm_pad.json"
        self.params = params
        self.origin = origin  # "built-in" or "user"

    def __repr__(self):
        return f"Preset({self.name!r}, {self.filename!r}, origin={self.origin!r})"


class PresetManager:
    """Manages synth presets stored as individual JSON files."""

    def __init__(self, presets_dir: Optional[Path] = None):
        if presets_dir is None:
            presets_dir = Path(__file__).parent.parent / "presets"
        self.presets_dir = presets_dir
        self.presets_dir.mkdir(parents=True, exist_ok=True)

        self.presets: list[Preset] = []
        self._reload()

    # ── Public API ──────────────────────────────────────────────

    def reload(self):
        """Reload presets from disk (call after save)."""
        self._reload()

    def count(self) -> int:
        return len(self.presets)

    def get(self, index: int) -> Optional[Preset]:
        if not self.presets:
            return None
        return self.presets[index % len(self.presets)]

    def find_index_by_filename(self, filename: str) -> int:
        """Return index of preset with given filename, or -1 if not found."""
        for i, p in enumerate(self.presets):
            if p.filename == filename:
                return i
        return -1

    def save_new(self, params: dict, name: Optional[str] = None) -> Preset:
        """Save params as a brand-new preset with a random musical name.

        If name is provided, use it; otherwise generate a unique musical name.
        """
        if name is None:
            name = self._unique_musical_name()
        return self._write_preset(name, params)

    def save_from_factory(self, factory_preset_name: str, factory_params: dict) -> Preset:
        """Create a user preset from a factory preset.

        This is called when user selects a factory preset.
        Creates a new user preset with "User: " prefix + factory preset name.

        Args:
            factory_preset_name: Name of the factory preset
            factory_params: Parameters from the factory preset

        Returns:
            New user Preset object with "User: " prefix
        """
        # Check if we already have a user copy of this factory preset
        user_name = f"User: {factory_preset_name}"
        existing_index = next(
            (i for i, p in enumerate(self.presets)
             if p.name == user_name and p.origin == "user"),
            None
        )

        if existing_index is not None:
            # Overwrite existing user copy
            preset = self.presets[existing_index]
            return self.save_overwrite(preset, factory_params)
        else:
            # Create new user preset
            return self.save_new(factory_params, name=user_name)

    def save_overwrite(self, preset: Preset, params: dict) -> Preset:
        """Overwrite an existing preset file with new params, keeping its name."""
        return self._write_preset(preset.name, params, filename=preset.filename)

    def extract_params(self, preset: Preset) -> dict:
        """Return a clean params dict from a preset, filling missing keys with defaults."""
        out = dict(DEFAULT_PARAMS)
        out.update({k: preset.params[k] for k in PARAM_KEYS if k in preset.params})
        return out

    # ── Internal helpers ─────────────────────────────────────────

    def _reload(self):
        """Load all presets with two-tier ordering:
        1. Built-in presets — alphabetically by filename (stable, predictable)
        2. User presets     — by file modification time, oldest first
                              so newly saved presets always appear at the end.
        """
        all_paths = list(self.presets_dir.glob("*.json"))

        builtin_paths = sorted(
            [p for p in all_paths if p.name in _BUILTIN_FILENAMES]
        )
        user_paths = sorted(
            [p for p in all_paths if p.name not in _BUILTIN_FILENAMES],
            key=lambda p: p.stat().st_mtime,
        )

        presets = []
        for path in builtin_paths + user_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                name = data.get("name", path.stem.replace("_", " ").title())
                origin = "built-in" if path.name in _BUILTIN_FILENAMES else "user"
                presets.append(Preset(name=name, filename=path.name, params=data, origin=origin))
            except Exception:
                pass  # skip malformed files
        self.presets = presets

    def _write_preset(self, name: str, params: dict, filename: Optional[str] = None) -> Preset:
        if filename is None:
            slug = re.sub(r"[^\w]", "_", name.lower())
            filename = f"{slug}.json"

        data = {"name": name}
        data.update({k: params.get(k, DEFAULT_PARAMS[k]) for k in PARAM_KEYS})

        path = self.presets_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self._reload()
        return Preset(name=name, filename=filename, params=data)

    def _unique_musical_name(self) -> str:
        existing_names = {p.name.lower() for p in self.presets}
        existing_files = {p.filename for p in self.presets}

        for _ in range(200):
            adj  = random.choice(_ADJECTIVES)
            noun1 = random.choice(_NOUNS)
            noun2 = random.choice(_NOUNS)
            # Avoid repeating the same word twice
            if noun1 == noun2:
                continue
            name = f"{adj} {noun1} {noun2}"
            slug = f"{adj}_{noun1}_{noun2}.json"
            if name.lower() not in existing_names and slug not in existing_files:
                return name

        # Fallback with number suffix
        adj  = random.choice(_ADJECTIVES)
        noun1 = random.choice(_NOUNS)
        suffix = random.randint(2, 999)
        return f"{adj} {noun1} {suffix}"
