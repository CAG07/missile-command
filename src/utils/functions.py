"""
Shared utility functions for Missile Command.

Provides fixed-point math helpers, distance calculations, and
collision detection routines used across models.

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

from src.config import (
    ATTACK_PACE_BASE,
    ATTACK_PACE_FACTOR,
    ATTACK_PACE_MIN,
    FIXED_POINT_SCALE,
    FIXED_POINT_SHIFT,
    POINTS_PER_REMAINING_ABM,
    POINTS_PER_SURVIVING_CITY,
    WAVE_SPEEDS,
)


# ── Fixed-point helpers (re-exported for convenience) ──────────────────────
# Canonical implementations live in src.models.missile; these are thin
# wrappers so callers outside ``models`` don't need to import from there.


def to_fixed(value: int) -> int:
    """Convert an integer to 8.8 fixed-point."""
    return value << FIXED_POINT_SHIFT


def from_fixed(value: int) -> int:
    """Truncate 8.8 fixed-point to integer."""
    return value >> FIXED_POINT_SHIFT


def distance_approx(x1: int, y1: int, x2: int, y2: int) -> int:
    """Fast octagonal distance approximation, capped at 255."""
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    if dx < dy:
        dx, dy = dy, dx
    dist = dx + ((3 * dy) >> 3)
    return min(dist, 255)


# ── Wave helpers ────────────────────────────────────────────────────────────


def get_wave_speed(wave_number: int) -> int:
    """Return the ICBM speed for a given wave (1-indexed)."""
    idx = min(wave_number - 1, len(WAVE_SPEEDS) - 1)
    return WAVE_SPEEDS[max(idx, 0)]


def get_attack_pace_altitude(wave_number: int) -> int:
    """Return the attack-pacing altitude for a given wave.

    Formula: 202 - 2 * wave_number, minimum 180.
    """
    alt = ATTACK_PACE_BASE - ATTACK_PACE_FACTOR * wave_number
    return max(alt, ATTACK_PACE_MIN)


# ── Scoring helpers ─────────────────────────────────────────────────────────


def calculate_wave_bonus(
    surviving_cities: int,
    remaining_abms: int,
) -> int:
    """Calculate end-of-wave bonus score.

    Points for surviving cities and remaining ABMs, matching the
    original arcade scoring.
    """
    return (
        surviving_cities * POINTS_PER_SURVIVING_CITY
        + remaining_abms * POINTS_PER_REMAINING_ABM
    )
