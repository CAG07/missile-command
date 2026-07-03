"""
Core game logic for Missile Command.

Orchestrates game state, score tracking, wave management, and
integrates all model subsystems (missiles, explosions, cities,
defenses).

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from src.config import (
    ATTACK_BATCH_SIZE,
    FLIER_INITIAL_DELAY_FRAMES,
    FLIER_START_WAVE,
    FLIER_TIMER_SCALE,
    MAX_CITIES_DESTROYED_PER_WAVE,
    MAX_ICBM_SLOTS,
    MAX_SMART_BOMBS,
    MIRV_ALTITUDE_HIGH,
    POINTS_PER_FLIER,
    POINTS_PER_ICBM,
    POINTS_PER_SMART_BOMB,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SMART_BOMB_CHANCE,
    SMART_BOMB_EVASION_RADIUS,
    SMART_BOMB_START_WAVE,
)
from src.models.city import CityManager
from src.models.defense import DefenseManager
from src.models.explosion import Explosion, ExplosionManager
from src.models.missile import (
    ABM,
    ICBM,
    Flier,
    MissileSlotManager,
    SmartBomb,
)
from src.ui.text import ScoreDisplay
from src.utils.functions import (
    calculate_wave_bonus,
    distance_approx,
    get_attack_pace_altitude,
    get_wave_speed,
)


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
    defenses: DefenseManager = field(default_factory=DefenseManager)
    score_display: ScoreDisplay = field(default_factory=ScoreDisplay)

    # Wave tracking
    icbms_remaining_this_wave: int = 0
    frame_count: int = 0
    flier_spawn_timer: int = 0
    flier_fire_cooldown: int = 0
    last_wave_bonus: int = 0

    # ── Wave lifecycle ──────────────────────────────────────────────────

    def start_wave(self) -> None:
        """Begin a new wave: restore defenses, cities, reset counters."""
        self.state = GameState.RUNNING
        self.defenses.restore_all()
        self.cities.start_wave()
        self.missiles.reset()
        self.explosions.reset()
        self.icbms_remaining_this_wave = self._icbms_for_wave()
        self.frame_count = 0
        self.flier_spawn_timer = FLIER_INITIAL_DELAY_FRAMES
        self.flier_fire_cooldown = 0

    def _icbms_for_wave(self) -> int:
        """Determine how many ICBMs to launch this wave."""
        return min(8 + self.wave_number * 2, 30)

    def end_wave(self) -> int:
        """End the current wave and return bonus score."""
        bonus = calculate_wave_bonus(
            self.cities.active_count,
            self.defenses.total_abm_count,
        )
        self.score_display.add(bonus)
        self.last_wave_bonus = bonus
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

        # 1. Smart bombs check for nearby explosions before moving.
        self._update_smart_bomb_evasion()

        # 2. Move all missiles / the flier.
        self.missiles.update_all()

        # 3. Missiles that just reached their targets detonate: spawn
        #    impact explosions and damage cities/silos. Must run before
        #    clear_inactive() so we can still see which slots arrived.
        self._process_arrivals()

        # 4. MIRV splits (mid-flight, altitude-gated).
        self._process_mirv_splits()

        # 5. Now safe to free slots vacated by arrivals/collisions.
        self.missiles.clear_inactive()

        # 6. Update explosions (one group per frame).
        updated_explosions = self.explosions.update()

        # 7. Collision: explosions vs ICBMs/smart bombs.
        icbm_positions = []
        for i, slot in enumerate(self.missiles.icbm_slots):
            if slot is not None and slot.is_active:
                icbm_positions.append((slot.current_x, slot.current_y, i))
        hit_indices = self.explosions.check_icbm_collisions(
            updated_explosions, icbm_positions
        )
        for idx in set(hit_indices):
            slot = self.missiles.icbm_slots[idx]
            if slot is not None and slot.is_active:
                pts = (
                    POINTS_PER_SMART_BOMB
                    if isinstance(slot, SmartBomb)
                    else POINTS_PER_ICBM
                )
                self.score_display.add(pts)
                slot.deactivate()

        # 8. Collision: explosions vs flier.
        flier = self.missiles.flier_slot
        if flier is not None and flier.is_active:
            for exp in updated_explosions:
                if exp.collides_with(flier.current_x, flier.altitude):
                    self.score_display.add(POINTS_PER_FLIER)
                    flier.deactivate()
                    break

        # 9. Bonus cities.
        self.cities.check_bonus(self.score_display.player_score)

        # 10. Game-over check.
        if self.cities.all_destroyed:
            self.state = GameState.GAME_OVER
            return self.state

        # 11. Mercy rule: never lose more than 3 cities in a wave; if
        #     the limit is hit and the player has no ABMs left, end the
        #     wave immediately (see $59fa).
        if (
            self.cities.cities_destroyed_this_wave >= MAX_CITIES_DESTROYED_PER_WAVE
            and self.defenses.total_abm_count == 0
            and self.missiles.active_abm_count == 0
        ):
            self.end_wave()
            return self.state

        # 12. Attack pacing: launch new ICBMs/smart bombs.
        self._update_attack_pacing()

        # 13. Flier spawn / flight / firing.
        self._update_flier()

        # 14. Normal wave-end check.
        if (
            self.icbms_remaining_this_wave <= 0
            and self.missiles.active_icbm_count == 0
            and self.explosions.active_count == 0
        ):
            self.end_wave()

        return self.state

    # ── Arrival / detonation handling ────────────────────────────────────

    def _process_arrivals(self) -> None:
        """Spawn impact explosions for missiles that just reached target."""
        for abm in self.missiles.abm_slots:
            if abm is not None and not abm.is_active:
                self.explosions.add(Explosion(center_x=abm.target_x, center_y=abm.target_y))

        for missile in self.missiles.icbm_slots:
            if missile is not None and not missile.is_active:
                self.explosions.add(
                    Explosion(center_x=missile.target_x, center_y=missile.target_y)
                )
                hit_city = self.cities.destroy_city_at(missile.target_x, missile.target_y)
                if not hit_city:
                    self.defenses.destroy_silo_at(missile.target_x, missile.target_y)

    # ── MIRV ──────────────────────────────────────────────────────────────

    def _process_mirv_splits(self) -> None:
        """Walk the ICBM table and split eligible missiles (see $5379/$56d1)."""
        if self.icbms_remaining_this_wave <= 0:
            return

        seen_above_high = False
        for missile in self.missiles.icbm_slots:
            if missile is None or not missile.is_active or not isinstance(missile, ICBM):
                continue

            if not missile.has_mirved and missile.can_mirv:
                eligible = ICBM.check_mirv_conditions(
                    missile,
                    active_icbm_count=self.missiles.active_icbm_count,
                    remaining_wave_icbms=self.icbms_remaining_this_wave,
                    any_above_high=seen_above_high,
                )
                if eligible:
                    targets = self._pick_targets(3)
                    children = missile.mirv(
                        targets,
                        self.missiles.active_icbm_count,
                        self.icbms_remaining_this_wave,
                    )
                    for child in children:
                        if self.missiles.add_icbm(child):
                            self.icbms_remaining_this_wave -= 1

            if missile.altitude > MIRV_ALTITUDE_HIGH:
                seen_above_high = True

    # ── Target selection (mercy-rule aware) ──────────────────────────────

    def _pick_targets(self, count: int = 1) -> list[tuple[int, int]]:
        """Choose up to *count* attack targets among cities and silos.

        Enforces the "never lose more than 3 cities per wave" rule by
        refusing to open fire on additional cities once the number of
        simultaneously-targeted cities would exceed the remaining
        allowance (see $5791).
        """
        max_city_targets = max(
            1, MAX_CITIES_DESTROYED_PER_WAVE - self.cities.cities_destroyed_this_wave
        )
        city_positions = [c.position for c in self.cities.active_cities]
        silo_positions = [s.position for s in self.defenses.silos if not s.is_destroyed]

        city_position_set = set(city_positions)
        targeted_cities = {
            (m.target_x, m.target_y)
            for m in self.missiles.icbm_slots
            if m is not None and m.is_active and (m.target_x, m.target_y) in city_position_set
        }

        # Update targeted_cities as we draw so a single multi-target call
        # (e.g. a MIRV burst) can't itself exceed the mercy-rule allowance.
        results: list[tuple[int, int]] = []
        for _ in range(count):
            if len(targeted_cities) >= max_city_targets:
                available_cities = [p for p in city_positions if p in targeted_cities]
            else:
                available_cities = city_positions

            candidates = available_cities + silo_positions
            if not candidates:
                candidates = city_positions + silo_positions
            if not candidates:
                break

            choice = random.choice(candidates)
            results.append(choice)
            if choice in city_position_set:
                targeted_cities.add(choice)
        return results

    # ── Attack pacing ─────────────────────────────────────────────────────

    def _highest_real_altitude(self) -> int:
        """Return the highest active ICBM's altitude above the ground.

        Inverted from screen-space Y (0 = top) so a freshly-spawned
        missile near the top of the screen reads as a high altitude,
        matching the disassembly's pacing gate ($5791).
        """
        best = 0
        for missile in self.missiles.icbm_slots:
            if missile is not None and missile.is_active:
                alt = SCREEN_HEIGHT - missile.current_y
                if alt > best:
                    best = alt
        return best

    def _update_attack_pacing(self) -> None:
        """Launch new ICBMs/smart bombs, gated by the wave's pace altitude."""
        if self.icbms_remaining_this_wave <= 0:
            return
        if self.missiles.active_icbm_count >= MAX_ICBM_SLOTS:
            return
        pace_altitude = get_attack_pace_altitude(self.wave_number)
        if self._highest_real_altitude() > pace_altitude:
            return

        launched = 0
        while (
            launched < ATTACK_BATCH_SIZE
            and self.icbms_remaining_this_wave > 0
            and self.missiles.active_icbm_count < MAX_ICBM_SLOTS
        ):
            targets = self._pick_targets(1)
            if not targets:
                break
            target_x, target_y = targets[0]
            entry_x = random.randint(0, SCREEN_WIDTH - 1)
            if not self._spawn_attack_missile(entry_x, 0, target_x, target_y):
                break
            launched += 1

    def _spawn_attack_missile(
        self, entry_x: int, entry_y: int, target_x: int, target_y: int
    ) -> bool:
        """Spawn either an ICBM or a SmartBomb from the wave's budget."""
        if self.icbms_remaining_this_wave <= 0:
            return False
        speed = get_wave_speed(self.wave_number)
        use_smart_bomb = (
            self.wave_number >= SMART_BOMB_START_WAVE
            and self.missiles.smart_bomb_count < MAX_SMART_BOMBS
            and random.random() < SMART_BOMB_CHANCE
        )
        missile: ICBM
        if use_smart_bomb:
            missile = SmartBomb(
                entry_x=entry_x, entry_y=entry_y,
                target_x=target_x, target_y=target_y,
                speed=speed, can_mirv=False,
            )
        else:
            missile = ICBM(
                entry_x=entry_x, entry_y=entry_y,
                target_x=target_x, target_y=target_y,
                speed=speed, can_mirv=True,
            )
        if self.missiles.add_icbm(missile):
            self.icbms_remaining_this_wave -= 1
            return True
        return False

    # ── Smart bomb evasion ────────────────────────────────────────────────

    def _update_smart_bomb_evasion(self) -> None:
        """Feed nearby explosion centers to active smart bombs."""
        centers = self.explosions.active_explosion_centers
        if not centers:
            for missile in self.missiles.icbm_slots:
                if isinstance(missile, SmartBomb) and missile.is_active:
                    missile.detect_explosions([])
            return
        for missile in self.missiles.icbm_slots:
            if isinstance(missile, SmartBomb) and missile.is_active:
                nearby = [
                    c for c in centers
                    if distance_approx(missile.current_x, missile.current_y, c[0], c[1])
                    <= SMART_BOMB_EVASION_RADIUS
                ]
                missile.detect_explosions(nearby)

    # ── Flier ─────────────────────────────────────────────────────────────

    def _update_flier(self) -> None:
        """Spawn, fly, and fire the single flier slot."""
        if self.wave_number < FLIER_START_WAVE:
            return

        flier = self.missiles.flier_slot
        if flier is None or not flier.is_active:
            if self.flier_spawn_timer > 0:
                self.flier_spawn_timer -= 1
                return
            new_flier = Flier.create_random(self.wave_number, SCREEN_WIDTH)
            self.missiles.set_flier(new_flier)
            self.flier_fire_cooldown = new_flier.firing_timer * FLIER_TIMER_SCALE
            return

        if flier.current_x < -8 or flier.current_x > SCREEN_WIDTH + 8:
            flier.deactivate()
            self.flier_spawn_timer = flier.resurrection_timer * FLIER_TIMER_SCALE
            return

        self.flier_fire_cooldown -= 1
        if self.flier_fire_cooldown <= 0:
            if self.icbms_remaining_this_wave > 0:
                targets = self._pick_targets(1)
                if targets:
                    speed = get_wave_speed(self.wave_number)
                    for shot in flier.fire(targets, speed=speed):
                        if self.missiles.add_icbm(shot):
                            self.icbms_remaining_this_wave -= 1
            self.flier_fire_cooldown = flier.firing_timer * FLIER_TIMER_SCALE

    # ── Player actions ──────────────────────────────────────────────────

    def fire_from_silo(
        self, silo_index: int, target_x: int, target_y: int
    ) -> bool:
        """Attempt to fire an ABM from the specified silo."""
        abm = self.defenses.fire(
            silo_index, target_x, target_y,
            self.missiles.active_abm_count,
        )
        if abm is None:
            return False
        return self.missiles.add_abm(abm)

    def fire_nearest(self, target_x: int, target_y: int) -> bool:
        """Fire from whichever silo is nearest to the target."""
        abm = self.defenses.fire_nearest(
            target_x, target_y,
            self.missiles.active_abm_count,
        )
        if abm is None:
            return False
        return self.missiles.add_abm(abm)

    # ── Spawn helpers (used directly by tests / scripted play) ───────────

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
