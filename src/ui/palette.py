"""
Color palette for Missile Command.

The arcade cycles a handful of per-wave palettes for the sky, ground,
and missile trails. This module provides a small rotating set of
palettes (RGB, since we render on modern hardware rather than the
original's indexed framebuffer) plus the flashing explosion colors
referenced by the disassembly ($61ed, colors #4/#5).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    """One wave's set of display colors."""

    sky: tuple[int, int, int]
    ground: tuple[int, int, int]
    city: tuple[int, int, int]
    city_destroyed: tuple[int, int, int]
    silo: tuple[int, int, int]
    abm_trail: tuple[int, int, int]
    icbm_trail: tuple[int, int, int]
    text: tuple[int, int, int]


# A short rotation of wave palettes, cycling by wave_number.
PALETTES: list[Palette] = [
    Palette(
        sky=(0, 0, 0), ground=(199, 128, 40), city=(120, 190, 255),
        city_destroyed=(60, 60, 60), silo=(255, 255, 255),
        abm_trail=(80, 180, 255), icbm_trail=(255, 80, 80), text=(255, 255, 255),
    ),
    Palette(
        sky=(10, 0, 20), ground=(180, 90, 160), city=(255, 200, 90),
        city_destroyed=(60, 60, 60), silo=(255, 255, 255),
        abm_trail=(255, 220, 90), icbm_trail=(255, 100, 180), text=(255, 255, 255),
    ),
    Palette(
        sky=(0, 10, 15), ground=(60, 170, 90), city=(255, 150, 60),
        city_destroyed=(60, 60, 60), silo=(255, 255, 255),
        abm_trail=(120, 255, 170), icbm_trail=(255, 210, 60), text=(255, 255, 255),
    ),
    Palette(
        sky=(15, 0, 0), ground=(210, 60, 60), city=(255, 255, 140),
        city_destroyed=(60, 60, 60), silo=(255, 255, 255),
        abm_trail=(255, 140, 140), icbm_trail=(140, 220, 255), text=(255, 255, 255),
    ),
]

#: The disassembly says explosions "rotate through all 8 possible
#: colors" at 30Hz -- on this era's hardware that's a 3-bit RGB palette
#: (each channel fully on or off), i.e. the 8 corners of the RGB cube.
#: Verified against missile-command-arcade.gif: sampled explosion pixels
#: came back as pure magenta (254,1,254), cyan (1,253,253), blue
#: (1,0,252), and white (254,254,254) -- exactly 4 of those 8 corners.
#: Black is excluded here since it's invisible against the black sky.
EXPLOSION_COLORS: list[tuple[int, int, int]] = [
    (255, 255, 255),  # white
    (0, 0, 255),      # blue
    (0, 255, 0),       # green
    (0, 255, 255),    # cyan
    (255, 0, 0),      # red
    (255, 0, 255),    # magenta
    (255, 255, 0),    # yellow
]

FLASH_COLORS: list[tuple[int, int, int]] = [
    (255, 255, 255),
    (0, 0, 0),
]


def get_palette(wave_number: int) -> Palette:
    """Return the palette for *wave_number* (1-indexed, cycling)."""
    idx = (max(wave_number, 1) - 1) % len(PALETTES)
    return PALETTES[idx]


def explosion_color(frame_count: int) -> tuple[int, int, int]:
    """Return the color-cycled explosion color for the current frame.

    Cycles at 30Hz (every 2 frames at 60Hz), matching the disassembly's
    IRQ-driven palette rotation.
    """
    idx = (frame_count // 2) % len(EXPLOSION_COLORS)
    return EXPLOSION_COLORS[idx]


def flash_color(frame_count: int) -> tuple[int, int, int]:
    """Return the flashing crosshair/warning color for the current frame."""
    idx = (frame_count // 8) % len(FLASH_COLORS)
    return FLASH_COLORS[idx]
