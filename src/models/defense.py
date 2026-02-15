"""
Defense silo model for Missile Command.

Implements the 3-silo system with per-silo ABM capacity and the
8-simultaneous-ABM launch limit from the original arcade hardware.

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.config import (
    MAX_ABM_SLOTS,
    NUM_SILOS,
    SILO_CAPACITY,
    SILO_POSITIONS,
)
from src.models.missile import ABM


# ── Defense Silo ────────────────────────────────────────────────────────────


@dataclass
class DefenseSilo:
    """A single defensive missile silo.

    Properties:
        silo_index: 0 = left, 1 = center, 2 = right
        position: (x, y) screen coordinates
        abm_count: current ABM supply (0-10)
        is_destroyed: whether silo has been hit
    """

    silo_index: int
    position_x: int
    position_y: int
    abm_count: int = SILO_CAPACITY
    is_destroyed: bool = False

    @property
    def position(self) -> tuple[int, int]:
        return (self.position_x, self.position_y)

    def can_fire(self) -> bool:
        """Return True if this silo can launch an ABM."""
        return not self.is_destroyed and self.abm_count > 0

    def fire(self, target_x: int, target_y: int) -> Optional[ABM]:
        """Create and return an ABM aimed at (*target_x*, *target_y*).

        Returns None if the silo cannot fire.

        Note: The caller must also check the global 8-ABM limit before
        accepting the returned ABM.
        """
        if not self.can_fire():
            return None
        self.abm_count -= 1
        return ABM(
            silo_index=self.silo_index,
            start_x=self.position_x,
            start_y=self.position_y,
            target_x=target_x,
            target_y=target_y,
        )

    def restore(self) -> None:
        """Restore the silo to full capacity for a new wave."""
        self.abm_count = SILO_CAPACITY
        self.is_destroyed = False

    def destroy(self) -> None:
        self.is_destroyed = True


# ── Defense Manager ─────────────────────────────────────────────────────────


@dataclass
class DefenseManager:
    """Manages all 3 defense silos and enforces the 8-ABM global limit.

    Provides silo selection, firing validation, and wave restoration.
    """

    silos: list[DefenseSilo] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.silos:
            self._init_silos()

    def _init_silos(self) -> None:
        """Create the default 3 silos from configuration."""
        for i in range(NUM_SILOS):
            pos = SILO_POSITIONS[i]
            self.silos.append(
                DefenseSilo(silo_index=i, position_x=pos[0], position_y=pos[1])
            )

    # Firing ──────────────────────────────────────────────────────────────

    def fire(
        self,
        silo_index: int,
        target_x: int,
        target_y: int,
        current_active_abms: int,
    ) -> Optional[ABM]:
        """Attempt to fire from silo *silo_index*.

        Returns None if:
        - silo index is invalid
        - the silo cannot fire (empty / destroyed)
        - 8 ABMs are already active
        """
        if current_active_abms >= MAX_ABM_SLOTS:
            return None
        if silo_index < 0 or silo_index >= len(self.silos):
            return None
        return self.silos[silo_index].fire(target_x, target_y)

    def fire_nearest(
        self,
        target_x: int,
        target_y: int,
        current_active_abms: int,
    ) -> Optional[ABM]:
        """Fire from the nearest silo that has ammo.

        Useful for single-turret play style.  Returns None if no silo
        can fire or the 8-ABM limit is reached.
        """
        if current_active_abms >= MAX_ABM_SLOTS:
            return None
        best: Optional[DefenseSilo] = None
        best_dist = float("inf")
        for silo in self.silos:
            if not silo.can_fire():
                continue
            d = abs(silo.position_x - target_x)
            if d < best_dist:
                best_dist = d
                best = silo
        if best is None:
            return None
        return best.fire(target_x, target_y)

    # Wave lifecycle ──────────────────────────────────────────────────────

    def restore_all(self) -> None:
        """Fully restore all silos at the start of a wave."""
        for silo in self.silos:
            silo.restore()

    # Queries ─────────────────────────────────────────────────────────────

    @property
    def total_abm_count(self) -> int:
        """Total unfired ABMs across all silos."""
        return sum(s.abm_count for s in self.silos)

    def get_silo(self, index: int) -> Optional[DefenseSilo]:
        if 0 <= index < len(self.silos):
            return self.silos[index]
        return None
