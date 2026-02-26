"""ABOUTME: Pattern file I/O manager - saves and loads patterns from JSON files.
ABOUTME: Handles disk persistence for drum patterns (load on demand, graceful fallback)."""

import json
import os
from pathlib import Path
from typing import Optional, Dict, List, Any


class PatternManager:
    """Manage pattern save/load from JSON files."""

    def __init__(self, patterns_dir: str = "patterns"):
        """Initialize pattern manager with patterns directory."""
        self.patterns_dir = Path(patterns_dir)
        # Create patterns directory if it doesn't exist
        self.patterns_dir.mkdir(parents=True, exist_ok=True)

    def save_pattern(
        self,
        pattern_num: int,
        pattern_data: List[List[Dict[str, Any]]],
        drum_names: List[str],
        bpm: int = 120,
        num_steps: int = 16,
        pre_scale: str = "4",
        drum_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        mute_state: Optional[List[bool]] = None,
        solo_state: Optional[List[bool]] = None,
        humanize_enabled: bool = False,
        humanize_velocity_amount: float = 0.15,
        fill_pattern_id: Optional[int] = None,
    ) -> bool:
        """
        Save a pattern to JSON file.

        Args:
            pattern_num: Pattern number (1-64)
            pattern_data: 8xN list of step dicts with active/velocity/note_length
            drum_names: List of drum names (should be 8 items matching pattern_data)
            bpm: Tempo in BPM
            num_steps: Number of steps in pattern
            pre_scale: PRE-SCALE steps per beat (1, 2, 4, 8, 16) as string
            drum_overrides: Optional dict of drum_name -> synth_params overrides
            mute_state: Optional list of bools indicating which drums are muted (per drum_idx)
            solo_state: Optional list of bools indicating which drums are soloed (per drum_idx)
            humanize_enabled: Whether humanization is enabled for this pattern
            humanize_velocity_amount: Velocity variation amount (0.0-0.3, default 0.15 = ±15%)
            fill_pattern_id: Optional fill pattern ID (1-16, or None for no fill)

        Returns:
            True if save successful, False otherwise
        """
        try:
            file_path = self.patterns_dir / f"pattern_{pattern_num:02d}.json"

            # Build JSON structure - save only the specified number of steps
            drums_data = []
            for drum_idx, drum_name in enumerate(drum_names):
                if drum_idx < len(pattern_data):
                    # Save only up to num_steps steps from this drum's pattern
                    steps = pattern_data[drum_idx][:num_steps]
                    drums_data.append(
                        {
                            "name": drum_name,
                            "steps": steps,  # List of dicts: {active, velocity, note_length}
                        }
                    )

            json_data = {
                "metadata": {
                    "bpm": bpm,
                    "num_steps": num_steps,
                    "pre_scale": pre_scale,
                    "humanize_enabled": humanize_enabled,
                    "humanize_velocity_amount": humanize_velocity_amount,
                    "fill_pattern_id": fill_pattern_id,
                },
                "drums": drums_data,
            }

            # Add drum overrides if present
            if drum_overrides:
                json_data["drum_overrides"] = drum_overrides

            # Add mute/solo state if present
            if mute_state:
                json_data["mute_state"] = mute_state
            if solo_state:
                json_data["solo_state"] = solo_state

            # Write to file
            with open(file_path, "w") as f:
                json.dump(json_data, f, indent=2)

            return True
        except Exception as e:
            # Silently fail for now (log in production)
            return False

    def load_pattern(
        self,
        pattern_num: int,
        drum_names: List[str],
        default_num_steps: int = 16,
    ) -> Optional[Dict[str, Any]]:
        """
        Load a pattern from JSON file.

        Args:
            pattern_num: Pattern number (1-64)
            drum_names: List of drum names to validate against
            default_num_steps: Default step count if not in file

        Returns:
            Dict with 'pattern_data' (8xN list), 'metadata', or None if not found/error
        """
        try:
            file_path = self.patterns_dir / f"pattern_{pattern_num:02d}.json"

            if not file_path.exists():
                # File doesn't exist - return None (caller will create empty pattern)
                return None

            with open(file_path, "r") as f:
                json_data = json.load(f)

            # Extract metadata
            metadata = json_data.get("metadata", {})
            bpm = metadata.get("bpm", 120)
            num_steps = metadata.get("num_steps", default_num_steps)
            pre_scale = metadata.get("pre_scale", "4")

            # Reconstruct pattern_data: 8 drums × num_steps steps
            pattern_data = []
            drums_data = json_data.get("drums", [])

            for drum_idx, drum_name in enumerate(drum_names):
                drum_pattern = []
                if drum_idx < len(drums_data):
                    drum_info = drums_data[drum_idx]
                    steps = drum_info.get("steps", [])
                    # Reconstruct to requested num_steps (may be more or less than saved)
                    for step_idx in range(num_steps):
                        if step_idx < len(steps):
                            step_data = steps[step_idx]
                            # Ensure step data has correct structure
                            drum_pattern.append(
                                {
                                    "active": step_data.get("active", False),
                                    "velocity": max(0, min(127, step_data.get("velocity", 100))),
                                    "note_length": max(0.0, min(1.0, step_data.get("note_length", 0.5))),
                                }
                            )
                        else:
                            # Pad with empty steps if requesting more than saved
                            drum_pattern.append(
                                {"active": False, "velocity": 100, "note_length": 0.5}
                            )
                else:
                    # Drum not in file, create empty
                    drum_pattern = [
                        {"active": False, "velocity": 100, "note_length": 0.5}
                        for _ in range(num_steps)
                    ]

                pattern_data.append(drum_pattern)

            # Load drum overrides if present (Phase 3 feature)
            drum_overrides = json_data.get("drum_overrides", {})

            # Load mute/solo state if present (per-pattern mute/solo toggles)
            mute_state = json_data.get("mute_state", [])
            solo_state = json_data.get("solo_state", [])

            # Load humanize settings if present (per-pattern humanization settings)
            humanize_enabled = metadata.get("humanize_enabled", False)
            humanize_velocity_amount = metadata.get("humanize_velocity_amount", 0.15)

            # Load fill pattern assignment if present (per-pattern fill selection)
            fill_pattern_id = metadata.get("fill_pattern_id")

            return {
                "pattern_data": pattern_data,
                "bpm": bpm,
                "num_steps": num_steps,
                "pre_scale": pre_scale,
                "drum_overrides": drum_overrides,
                "mute_state": mute_state,
                "solo_state": solo_state,
                "humanize_enabled": humanize_enabled,
                "humanize_velocity_amount": humanize_velocity_amount,
                "fill_pattern_id": fill_pattern_id,
            }
        except Exception as e:
            # Error reading/parsing file - return None (caller will create empty)
            return None

    def pattern_exists(self, pattern_num: int) -> bool:
        """Check if a pattern file exists on disk."""
        file_path = self.patterns_dir / f"pattern_{pattern_num:02d}.json"
        return file_path.exists()

    def delete_pattern(self, pattern_num: int) -> bool:
        """Delete a pattern file."""
        try:
            file_path = self.patterns_dir / f"pattern_{pattern_num:02d}.json"
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception:
            return False

    def get_pattern_info(self, pattern_num: int) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a pattern without loading full step data.
        Useful for pattern selector UI.
        """
        try:
            file_path = self.patterns_dir / f"pattern_{pattern_num:02d}.json"
            if not file_path.exists():
                return {"exists": False}

            with open(file_path, "r") as f:
                json_data = json.load(f)

            metadata = json_data.get("metadata", {})
            return {
                "exists": True,
                "bpm": metadata.get("bpm", 120),
                "num_steps": metadata.get("num_steps", 16),
                "pre_scale": metadata.get("pre_scale", "4"),
            }
        except Exception:
            return {"exists": False}
