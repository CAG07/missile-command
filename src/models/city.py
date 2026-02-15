"""
City model for Missile Command.

Implements individual cities and a CityManager that enforces the
original arcade rules:

- Configurable initial count (DIP-switch: 4-7, default 6 marathon)
- 3-city-per-wave destruction limit
- Bonus cities awarded every N points (default 10,000)
- Random crater replacement for destroyed cities
- Bonus city count stored in a single 8-bit value (can overflow at 256)

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from src.config import (
    BONUS_CITY_POINTS,
    CITY_POSITIONS,
    MAX_CITIES_DESTROYED_PER_WAVE,
    NUM_CITIES_DEFAULT,
)


# ── City ────────────────────────────────────────────────────────────────────


@dataclass
class City:
    """A single city on the ground line.

    Properties mirror the original arcade: each city has a fixed
    position and can be destroyed or restored between waves.
    """

    position_x: int
    position_y: int
    is_destroyed: bool = False
    is_active: bool = True

    @property
    def position(self) -> tuple[int, int]:
        return (self.position_x, self.position_y)

    def destroy(self) -> None:
        """Mark the city as destroyed."""
        self.is_destroyed = True
        self.is_active = False

    def restore(self) -> None:
        """Restore the city for a new wave."""
        self.is_destroyed = False
        self.is_active = True


# ── City Manager ────────────────────────────────────────────────────────────


@dataclass
class CityManager:
    """Manages all cities, bonus awards, and per-wave destruction limits.

    Tracks on-screen cities and banked bonus cities.  The bonus count is
    stored as a single 8-bit value that can overflow at 256, matching
    the original hardware behaviour.
    """

    cities: list[City] = field(default_factory=list)
    bonus_cities: int = 0             # banked bonus cities (8-bit, wraps at 256)
    bonus_threshold: int = BONUS_CITY_POINTS
    cities_destroyed_this_wave: int = 0

    # Track the cumulative score last time we checked for bonus awards
    _last_bonus_score: int = 0

    def __post_init__(self) -> None:
        if not self.cities:
            self._init_cities()

    def _init_cities(self) -> None:
        """Create the default set of cities from configuration."""
        for i in range(min(NUM_CITIES_DEFAULT, len(CITY_POSITIONS))):
            pos = CITY_POSITIONS[i]
            self.cities.append(City(position_x=pos[0], position_y=pos[1]))

    # Wave lifecycle ──────────────────────────────────────────────────────

    def start_wave(self) -> None:
        """Restore cities and reset the per-wave destruction counter."""
        self.cities_destroyed_this_wave = 0
        for city in self.cities:
            city.restore()

    # Destruction ─────────────────────────────────────────────────────────

    def destroy_city(self, index: int) -> bool:
        """Attempt to destroy city at *index*.

        Returns False if the 3-per-wave limit has been reached or the
        city is already destroyed.
        """
        if index < 0 or index >= len(self.cities):
            return False
        city = self.cities[index]
        if city.is_destroyed:
            return False
        if self.cities_destroyed_this_wave >= MAX_CITIES_DESTROYED_PER_WAVE:
            return False
        city.destroy()
        self.cities_destroyed_this_wave += 1
        return True

    def destroy_city_at(self, x: int, y: int, radius: int = 10) -> bool:
        """Destroy the first active city within *radius* of (*x*, *y*).

        Enforces the 3-per-wave limit.
        """
        for i, city in enumerate(self.cities):
            if city.is_destroyed:
                continue
            dx = abs(city.position_x - x)
            dy = abs(city.position_y - y)
            if dx <= radius and dy <= radius:
                return self.destroy_city(i)
        return False

    # Bonus cities ────────────────────────────────────────────────────────

    def check_bonus(self, current_score: int) -> int:
        """Award bonus cities based on score.

        Multiple can be awarded in a single wave.  Returns the number
        of new bonus cities awarded this call.
        """
        if self.bonus_threshold <= 0:
            return 0
        awarded = 0
        while current_score - self._last_bonus_score >= self.bonus_threshold:
            self._last_bonus_score += self.bonus_threshold
            # 8-bit overflow matching original hardware
            self.bonus_cities = (self.bonus_cities + 1) & 0xFF
            awarded += 1
        return awarded

    def replace_random_crater(self) -> bool:
        """Replace a random destroyed city with a bonus city.

        Returns True if a replacement was made.
        """
        if self.bonus_cities <= 0:
            return False
        craters = [
            i for i, c in enumerate(self.cities) if c.is_destroyed
        ]
        if not craters:
            return False
        idx = random.choice(craters)
        self.cities[idx].restore()
        self.bonus_cities = (self.bonus_cities - 1) & 0xFF
        return True

    # Queries ─────────────────────────────────────────────────────────────

    @property
    def active_cities(self) -> list[City]:
        return [c for c in self.cities if not c.is_destroyed]

    @property
    def active_count(self) -> int:
        return len(self.active_cities)

    @property
    def total_cities(self) -> int:
        """On-screen active + banked bonus cities."""
        return self.active_count + self.bonus_cities

    @property
    def all_destroyed(self) -> bool:
        return self.active_count == 0 and self.bonus_cities == 0

    @property
    def destroyed_cities(self) -> list[City]:
        return [c for c in self.cities if c.is_destroyed]
