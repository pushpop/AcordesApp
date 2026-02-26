"""ABOUTME: PRE-SCALE timing for TR-909 drum machine sequencer resolution.
ABOUTME: Determines how many steps per beat (quarter note) for fundamental grid subdivision."""

from enum import Enum


class PreScale(Enum):
    """Available PRE-SCALE values for sequencer step resolution."""
    SCALE_1 = 1      # 1 step per beat
    SCALE_2 = 2      # 2 steps per beat
    SCALE_4 = 4      # 4 steps per beat (default - standard 16-step pattern = 4 beats)
    SCALE_8 = 8      # 8 steps per beat
    SCALE_16 = 16    # 16 steps per beat


# Ordered list of pre-scale values for cycling
PRE_SCALE_VALUES = [PreScale.SCALE_1, PreScale.SCALE_2, PreScale.SCALE_4, PreScale.SCALE_8, PreScale.SCALE_16]


def get_beat_position(step: int, pre_scale: int) -> tuple:
    """
    Calculate beat and position within beat for a given step.

    Args:
        step: Step index (0-based)
        pre_scale: Steps per beat (1, 2, 4, 8, or 16)

    Returns:
        Tuple of (beat_number, position_in_beat)
        Example: step=5 with pre_scale=2 returns (2, 1) - beat 2, position 1
    """
    beat = step // pre_scale
    position = step % pre_scale
    return (beat, position)


def get_pre_scale_name(pre_scale: PreScale) -> str:
    """Get human-readable name for a PRE-SCALE value."""
    pre_scale_names = {
        PreScale.SCALE_1: "1 step/beat",
        PreScale.SCALE_2: "2 steps/beat",
        PreScale.SCALE_4: "4 steps/beat",
        PreScale.SCALE_8: "8 steps/beat",
        PreScale.SCALE_16: "16 steps/beat",
    }
    return pre_scale_names.get(pre_scale, "Unknown")
