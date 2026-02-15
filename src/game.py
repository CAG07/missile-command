"""
Core game logic for Missile Command.

Orchestrates game state, score tracking, wave management, and
integrates all model subsystems (missiles, explosions, cities,
defences).

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from src.config import (
    BONUS_CITY_POINTS,
    POINTS_PER_ICBM,
    POINTS_PER_SMART_BOMB,
    POINTS_PER_FLIER,
    SCREEN_WIDTH,
    WAVE_SPEEDS,
)
from src.models.city import CityManager
from src.models.defence import DefenceManager
from src.models.explosion import ExplosionManager
from src.models.missile import (
    ABM,
    ICBM,
    Flier,
    MissileSlotManager,
    SmartBomb,
)
from src.ui.text import ScoreDisplay
from src.utils.functions import calculate_wave_bonus, get_wave_speed


# ── Game states ─────────────────────────────────────────────────────────────


class GameState(Enum):
    ATTRACT = auto()
    RUNNING = auto()
    WAVE_END = auto()
    GAME_OVER = auto()


# ── Game ────────────────────────────────────────────────────────────────────


@dataclass
class Game:
    """Top-level game controller.

    Holds all subsystem managers and drives the per-frame update loop
    at 60 Hz.
    """

    wave_number: int = 1
    state: GameState = GameState.ATTRACT

    # Subsystems
    missiles: MissileSlotManager = field(default_factory=MissileSlotManager)
    explosions: ExplosionManager = field(default_factory=ExplosionManager)
    cities: CityManager = field(default_factory=CityManager)
    defences: DefenceManager = field(default_factory=DefenceManager)
    score_display: ScoreDisplay = field(default_factory=ScoreDisplay)

    # Wave tracking
    icbms_remaining_this_wave: int = 0
    frame_count: int = 0

    # ── Wave lifecycle ──────────────────────────────────────────────────

    def start_wave(self) -> None:
        """Begin a new wave: restore defences, cities, reset counters."""
        self.state = GameState.RUNNING
        self.defences.restore_all()
        self.cities.start_wave()
        self.missiles.reset()
        self.explosions.reset()
        self.icbms_remaining_this_wave = self._icbms_for_wave()
        self.frame_count = 0

    def _icbms_for_wave(self) -> int:
        """Determine how many ICBMs to launch this wave."""
        return min(8 + self.wave_number * 2, 30)

    def end_wave(self) -> int:
        """End the current wave and return bonus score."""
        bonus = calculate_wave_bonus(
            self.cities.active_count,
            self.defences.total_abm_count,
        )
        self.score_display.add(bonus)
        self.cities.check_bonus(self.score_display.player_score)
        self.wave_number += 1
        self.state = GameState.WAVE_END
        return bonus

    # ── Per-frame update ────────────────────────────────────────────────

    def update(self) -> GameState:
        """Advance the game by one frame (1/60 s).

        Returns the current GameState after the update.
        """
        if self.state != GameState.RUNNING:
            return self.state

        self.frame_count += 1

        # 1. Update all missiles
        self.missiles.update_all()
        self.missiles.clear_inactive()

        # 2. Update explosions (one group per frame)
        updated_explosions = self.explosions.update()

        # 3. Collision: explosions vs ICBMs
        icbm_positions = []
        for i, slot in enumerate(self.missiles.icbm_slots):
            if slot is not None and slot.is_active:
                icbm_positions.append(
                    (slot.current_x, slot.current_y, i)
                )
        hit_indices = self.explosions.check_icbm_collisions(
            updated_explosions, icbm_positions
        )
        for idx in hit_indices:
            slot = self.missiles.icbm_slots[idx]
            if slot is not None and slot.is_active:
                pts = (
                    POINTS_PER_SMART_BOMB
                    if isinstance(slot, SmartBomb)
                    else POINTS_PER_ICBM
                )
                self.score_display.add(pts)
                slot.deactivate()

        # 4. Collision: explosions vs flier
        flier = self.missiles.flier_slot
        if flier is not None and flier.is_active:
            for exp in updated_explosions:
                if exp.collides_with(flier.current_x, flier.altitude):
                    self.score_display.add(POINTS_PER_FLIER)
                    flier.deactivate()
                    break

        # 5. Collision: ICBM detonations vs cities
        for slot in self.missiles.icbm_slots:
            if slot is not None and not slot.is_active:
                self.cities.destroy_city_at(slot.current_x, slot.current_y)

        # 6. Check bonus cities
        self.cities.check_bonus(self.score_display.player_score)

        # 7. Check game-over / wave-end conditions
        if self.cities.all_destroyed:
            self.state = GameState.GAME_OVER
            return self.state

        if (
            self.icbms_remaining_this_wave <= 0
            and self.missiles.active_icbm_count == 0
            and self.explosions.active_count == 0
        ):
            self.end_wave()

        return self.state

    # ── Player actions ──────────────────────────────────────────────────

    def fire_from_silo(
        self, silo_index: int, target_x: int, target_y: int
    ) -> bool:
        """Attempt to fire an ABM from the specified silo."""
        abm = self.defences.fire(
            silo_index, target_x, target_y,
            self.missiles.active_abm_count,
        )
        if abm is None:
            return False
        return self.missiles.add_abm(abm)

    def fire_nearest(self, target_x: int, target_y: int) -> bool:
        """Fire from whichever silo is nearest to the target."""
        abm = self.defences.fire_nearest(
            target_x, target_y,
            self.missiles.active_abm_count,
        )
        if abm is None:
            return False
        return self.missiles.add_abm(abm)

    # ── Spawn helpers (called by wave pacing logic) ─────────────────────

    def spawn_icbm(
        self,
        entry_x: int,
        entry_y: int,
        target_x: int,
        target_y: int,
        can_mirv: bool = False,
    ) -> bool:
        """Spawn an incoming ICBM if slots and wave budget allow."""
        if self.icbms_remaining_this_wave <= 0:
            return False
        speed = get_wave_speed(self.wave_number)
        icbm = ICBM(
            entry_x=entry_x,
            entry_y=entry_y,
            target_x=target_x,
            target_y=target_y,
            speed=speed,
            can_mirv=can_mirv,
        )
        if self.missiles.add_icbm(icbm):
            self.icbms_remaining_this_wave -= 1
            return True
        return False
