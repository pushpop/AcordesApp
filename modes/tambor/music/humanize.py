"""ABOUTME: Humanize module for adding natural velocity variations to drum hits.
ABOUTME: Applies subtle randomization to make mechanical patterns sound more organic."""

import random
from typing import Optional


class Humanizer:
    """Apply subtle velocity variations to drum hits for natural-sounding grooves."""

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize humanizer with optional random seed for reproducibility.

        Args:
            seed: Optional random seed (useful for testing reproducible variations)
        """
        if seed is not None:
            random.seed(seed)

    def humanize_velocity(
        self,
        velocity_amount: float,
        velocity: int = 100
    ) -> int:
        """
        Apply humanization to drum velocity.

        This method adds random velocity variation to make drum hits sound less
        mechanical and more like a human drummer who naturally varies hit intensity.

        Args:
            velocity_amount: Max velocity variation ratio (0.0-0.3)
                - 0.0 = no variation (returns original velocity)
                - 0.15 = ±15% variation (default)
                - 0.3 = ±30% variation (maximum)
            velocity: Base velocity (0-127, default 100)

        Returns:
            Humanized velocity (1-127), always within valid MIDI range

        Examples:
            >>> h = Humanizer()
            >>> h.humanize_velocity(0.0, 100)  # No variation
            100
            >>> # With amount > 0, returns randomized velocity (±amount%)
        """
        # No variation requested - return original velocity
        if velocity_amount <= 0:
            return velocity

        # Calculate variation range (±amount% of velocity)
        variation = velocity * velocity_amount
        variation_range = random.uniform(-variation, variation)
        humanized_velocity = int(velocity + variation_range)

        # Clamp to valid MIDI range (1-127)
        # Note: Use 1 as minimum instead of 0 to ensure drum triggers
        return max(1, min(127, humanized_velocity))
