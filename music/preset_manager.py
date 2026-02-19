"""Synth preset manager — load, save, and cycle through presets."""
import json
import random
import re
from pathlib import Path
from typing import Optional

# Factory preset filenames — always shown first, sorted alphabetically.
# Any file NOT in this set is treated as a user preset and appended in
# creation-time order (oldest → newest), so new saves always go to the end.
_FACTORY_FILENAMES = {
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
    "frozen", "sharp", "gentle", "distant", "heavy",
    # European Portuguese
    "escuro", "suave", "antigo", "dourado", "partido", "vazio", "nebuloso",
    "fundo", "sombrio", "brilhante", "calmo", "perdido", "eterno", "velado",
]

_NOUNS = [
    # English
    "reed", "fifth", "chord", "wave", "drift", "bell", "pulse", "pad",
    "string", "key", "echo", "tone", "veil", "dawn", "bloom",
    "harp", "bass", "fade", "crest", "flute",
    # European Portuguese
    "corda", "onda", "sino", "pulso", "acorde", "eco", "tom", "aurora",
    "ventos", "nevoa", "som", "bruma", "ritmo", "voz", "marcha",
]

# Default parameter values — mirrors SynthEngine.__init__ defaults
DEFAULT_PARAMS: dict = {
    "waveform": "sine",
    "octave": 0,
    "amp_level": 0.75,
    "cutoff": 2000.0,
    "hpf_cutoff": 20.0,
    "resonance": 0.3,
    "filter_mode": "ladder",
    "attack": 0.01,
    "decay": 0.2,
    "sustain": 0.7,
    "release": 0.1,
    "intensity": 0.8,
    "rank2_enabled": False,
    "rank2_waveform": "sawtooth",
    "rank2_detune": 5.0,
    "rank2_mix": 0.5,
    "sine_mix": 0.0,
    "lfo_freq": 1.0,
    "lfo_vco_mod": 0.0,
    "lfo_vcf_mod": 0.0,
    "lfo_vca_mod": 0.0,
}

PARAM_KEYS = list(DEFAULT_PARAMS.keys())


class Preset:
    """A single preset entry."""

    def __init__(self, name: str, filename: str, params: dict):
        self.name = name
        self.filename = filename  # basename, e.g. "warm_pad.json"
        self.params = params

    def __repr__(self):
        return f"Preset({self.name!r}, {self.filename!r})"


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

    def save_new(self, params: dict) -> Preset:
        """Save params as a brand-new preset with a random musical name."""
        name = self._unique_musical_name()
        return self._write_preset(name, params)

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
        1. Factory presets — alphabetically by filename (stable, predictable)
        2. User presets    — by file modification time, oldest first
                             so newly saved presets always appear at the end.
        """
        all_paths = list(self.presets_dir.glob("*.json"))

        factory_paths = sorted(
            [p for p in all_paths if p.name in _FACTORY_FILENAMES]
        )
        user_paths = sorted(
            [p for p in all_paths if p.name not in _FACTORY_FILENAMES],
            key=lambda p: p.stat().st_mtime,
        )

        presets = []
        for path in factory_paths + user_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                name = data.get("name", path.stem.replace("_", " ").title())
                presets.append(Preset(name=name, filename=path.name, params=data))
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

        for _ in range(100):
            adj = random.choice(_ADJECTIVES)
            noun = random.choice(_NOUNS)
            name = f"{adj} {noun}"
            slug = f"{adj}_{noun}.json"
            if name.lower() not in existing_names and slug not in existing_files:
                return name

        # Fallback with number suffix
        adj = random.choice(_ADJECTIVES)
        noun = random.choice(_NOUNS)
        suffix = random.randint(2, 99)
        return f"{adj} {noun} {suffix}"
