"""ABOUTME: Timing modes for drum machine sequencer effects.
ABOUTME: Provides swing, shuffle, and custom timing offset calculations."""

from enum import Enum
from typing import Dict, Callable, Optional


class TimingMode(Enum):
    """Available timing modes for the sequencer."""
    STRAIGHT = "straight"      # No timing variation
    SWING_50 = "swing_50"       # Swing with 50% offset
    SWING_66 = "swing_66"       # Swing with 66% offset
    SHUFFLE = "shuffle"         # Shuffle feel (similar to swing with specific ratio)
    HUMANIZE = "humanize"       # Random timing variations (future)


class TimingEngine:
    """
    Manages timing modes and calculates step timing offsets.

    Timing offsets are applied to even-numbered steps (1, 3, 5, 7...)
    to create swing, shuffle, and humanized feels.
    """

    def __init__(self, mode: TimingMode = TimingMode.STRAIGHT, swing_amount: float = 0.5):
        """
        Initialize the timing engine.

        Args:
            mode: TimingMode enum value (STRAIGHT, SWING_50, SWING_66, SHUFFLE)
            swing_amount: Custom swing percentage (0.0 = no swing, 1.0 = max swing)
                         Only used when mode is STRAIGHT with custom swing applied
        """
        self.mode = mode
        self.swing_amount = max(0.0, min(1.0, swing_amount))  # Clamp 0.0-1.0
        self._mode_functions: Dict[TimingMode, Callable] = {
            TimingMode.STRAIGHT: self._timing_straight,
            TimingMode.SWING_50: self._timing_swing_50,
            TimingMode.SWING_66: self._timing_swing_66,
            TimingMode.SHUFFLE: self._timing_shuffle,
        }

    def set_mode(self, mode: TimingMode):
        """Set the timing mode."""
        self.mode = mode

    def set_swing_amount(self, amount: float):
        """
        Set custom swing amount (0.0-1.0).

        Args:
            amount: Swing percentage (0.0 = straight, 1.0 = maximum swing)
        """
        self.swing_amount = max(0.0, min(1.0, amount))

    def get_step_offset(self, step: int, step_duration: float) -> float:
        """
        Calculate timing offset for a step.

        Args:
            step: Step index (0-based)
            step_duration: Duration of one step in seconds

        Returns:
            Timing offset in seconds (positive delays the step)
        """
        if self.mode not in self._mode_functions:
            return 0.0

        return self._mode_functions[self.mode](step, step_duration)

    def _timing_straight(self, step: int, step_duration: float) -> float:
        """Straight timing: no offset."""
        return 0.0

    def _timing_swing_50(self, step: int, step_duration: float) -> float:
        """Swing 50%: delay odd steps by 50% of step duration."""
        # Even steps (0, 2, 4...) = on beat
        # Odd steps (1, 3, 5...) = delayed by 50% of step
        if step % 2 == 1:  # Odd step
            return step_duration * 0.5
        return 0.0

    def _timing_swing_66(self, step: int, step_duration: float) -> float:
        """Swing 66%: delay odd steps by 66% of step duration (2/3)."""
        # Even steps (0, 2, 4...) = on beat
        # Odd steps (1, 3, 5...) = delayed by 66% of step
        if step % 2 == 1:  # Odd step
            return step_duration * (2.0 / 3.0)
        return 0.0

    def _timing_shuffle(self, step: int, step_duration: float) -> float:
        """Shuffle: triplet-based timing (delay by 1/3 of step on odd steps)."""
        # Create a shuffle feel using triplet rhythm
        # Even steps on beat, odd steps delayed by 1/3
        if step % 2 == 1:  # Odd step
            return step_duration * (1.0 / 3.0)
        return 0.0

    def get_mode_name(self) -> str:
        """Get human-readable name of current mode."""
        mode_names = {
            TimingMode.STRAIGHT: "Straight",
            TimingMode.SWING_50: "Swing 50%",
            TimingMode.SWING_66: "Swing 66%",
            TimingMode.SHUFFLE: "Shuffle",
        }
        return mode_names.get(self.mode, "Unknown")

    def get_all_modes(self):
        """Get list of all available timing modes."""
        return list(TimingMode)


def get_timing_modes_list() -> list:
    """Get list of all available timing mode names."""
    return [mode.value for mode in TimingMode if mode != TimingMode.HUMANIZE]
