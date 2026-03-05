# ABOUTME: Velocity curve lookup tables that remap MIDI input velocity (0-127).
# ABOUTME: Five curves map raw MIDI velocity to expressive output velocity.

import math

# ---------------------------------------------------------------------------
# Build 128-entry lookup tables (index = raw MIDI velocity 0-127,
# value = output MIDI velocity 0-127).
# ---------------------------------------------------------------------------

def _build_linear() -> list[int]:
    """1:1 identity mapping — no remapping."""
    return list(range(128))


def _build_soft() -> list[int]:
    """Logarithmic curve — gentle playing triggers fuller volume.
    Good for pianists who need the synth to respond at low velocities."""
    out = []
    for v in range(128):
        if v == 0:
            out.append(0)
        else:
            # Square-root compression: boosts low velocities
            mapped = int(round(127.0 * math.sqrt(v / 127.0)))
            out.append(min(127, max(0, mapped)))
    return out


def _build_normal() -> list[int]:
    """Mild S-curve — gentle compression at the extremes, nearly linear in middle.
    Balanced response suitable for most playing styles."""
    out = []
    for v in range(128):
        if v == 0:
            out.append(0)
        else:
            # Blend: 50% linear + 50% soft (sqrt)
            linear = v / 127.0
            soft = math.sqrt(v / 127.0)
            mapped = int(round(127.0 * (0.5 * linear + 0.5 * soft)))
            out.append(min(127, max(0, mapped)))
    return out


def _build_strong() -> list[int]:
    """Exponential curve — you must play harder to reach full velocity.
    Good for leads and expressive playing where dynamics matter."""
    out = []
    for v in range(128):
        if v == 0:
            out.append(0)
        else:
            # Power curve (gamma > 1 darkens response)
            mapped = int(round(127.0 * ((v / 127.0) ** 1.8)))
            out.append(min(127, max(0, mapped)))
    return out


def _build_very_strong() -> list[int]:
    """Aggressive exponential curve — only forte playing produces loud output.
    Best for percussion and very dynamic playing styles."""
    out = []
    for v in range(128):
        if v == 0:
            out.append(0)
        else:
            mapped = int(round(127.0 * ((v / 127.0) ** 3.0)))
            out.append(min(127, max(0, mapped)))
    return out


# Pre-built lookup tables, keyed by the curve name used in config_manager
VELOCITY_CURVES: dict[str, list[int]] = {
    "Linear":      _build_linear(),
    "Soft":        _build_soft(),
    "Normal":      _build_normal(),
    "Strong":      _build_strong(),
    "Very Strong": _build_very_strong(),
}


def apply_curve(raw_velocity: int, curve_name: str) -> int:
    """Map a raw MIDI velocity through the named curve.

    Args:
        raw_velocity: Input MIDI velocity (0-127).
        curve_name:   One of "Linear", "Soft", "Normal", "Strong", "Very Strong".

    Returns:
        Remapped MIDI velocity (0-127).
    """
    table = VELOCITY_CURVES.get(curve_name, VELOCITY_CURVES["Linear"])
    idx = max(0, min(127, raw_velocity))
    return table[idx]
