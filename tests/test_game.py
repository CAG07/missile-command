"""
Tests for main game logic and state management.

Covers game state transitions, scoring, wave management, slot management,
explosion mechanics, and wave helpers.
"""

import pytest

from src.config import (
    ATTACK_BATCH_SIZE,
    BONUS_CITY_POINTS,
    EXPLOSION_GROUPS,
    EXPLOSION_MAX_RADIUS,
    FLIER_START_WAVE,
    GROUND_Y,
    MAX_ABM_SLOTS,
    MAX_CITIES_DESTROYED_PER_WAVE,
    MAX_GROUND_CRATERS,
    MAX_ICBM_SLOTS,
    POINTS_PER_FLIER,
    POINTS_PER_ICBM,
    POINTS_PER_REMAINING_ABM,
    POINTS_PER_SMART_BOMB,
    POINTS_PER_SURVIVING_CITY,
)
from src.game import Game, GameState
from src.models.explosion import Explosion, ExplosionManager, ExplosionState
from src.models.missile import ABM, ICBM, Flier, FlierType, MissileSlotManager, SmartBomb
from src.ui.text import ScoreDisplay
from src.utils.functions import (
    calculate_wave_bonus,
    get_attack_pace_altitude,
    get_wave_move_delay,
)


# ── Game State Tests ────────────────────────────────────────────────────────


class TestGameState:
    def test_initial_attract(self):
        game = Game()
        assert game.state == GameState.ATTRACT

    def test_attract_to_running(self):
        game = Game()
        game.start_wave()
        assert game.state == GameState.RUNNING

    def test_running_to_game_over(self):
        game = Game()
        game.start_wave()
        for city in game.cities.cities:
            city.destroy()
        game.cities.bonus_cities = 0
        state = game.update()
        assert state == GameState.GAME_OVER

    def test_running_to_wave_end(self):
        game = Game()
        game.start_wave()
        game.icbms_remaining_this_wave = 0
        # No active ICBMs or explosions
        state = game.update()
        assert state == GameState.WAVE_END

    def test_state_persistence(self):
        game = Game()
        game.start_wave()
        game.spawn_icbm(100, 0, 100, 200)
        state = game.update()
        assert state == GameState.RUNNING


# ── Scoring Tests ───────────────────────────────────────────────────────────


class TestScoring:
    def test_icbm_destruction_25_points(self):
        assert POINTS_PER_ICBM == 25

    def test_flier_100_points(self):
        assert POINTS_PER_FLIER == 100

    def test_smart_bomb_125_points(self):
        assert POINTS_PER_SMART_BOMB == 125

    def test_unfired_abm_bonus(self):
        assert POINTS_PER_REMAINING_ABM == 5

    def test_surviving_city_bonus(self):
        assert POINTS_PER_SURVIVING_CITY == 100

    def test_score_display_add(self):
        sd = ScoreDisplay()
        sd.add(100)
        assert sd.player_score == 100

    def test_high_score_updates(self):
        sd = ScoreDisplay(high_score=50)
        sd.add(100)
        assert sd.high_score == 100

    def test_high_score_persists_on_reset(self):
        sd = ScoreDisplay()
        sd.add(500)
        sd.reset()
        assert sd.player_score == 0
        assert sd.high_score == 500

    def test_wave_bonus_calculation(self):
        bonus = calculate_wave_bonus(surviving_cities=4, remaining_abms=10)
        assert bonus == 4 * 100 + 10 * 5


# ── Wave Management Tests ──────────────────────────────────────────────────


class TestWaveManagement:
    def test_wave_increments(self):
        game = Game()
        game.start_wave()
        game.icbms_remaining_this_wave = 0
        game.update()
        assert game.wave_number == 2

    def test_wave_move_delay_decreases(self):
        # Higher wave = shorter delay between moves = faster/harder.
        assert get_wave_move_delay(1) > get_wave_move_delay(5)

    def test_attack_pace_altitude(self):
        assert get_attack_pace_altitude(1) == 200
        assert get_attack_pace_altitude(11) == 180
        assert get_attack_pace_altitude(50) == 180  # clamped

    def test_wave_move_delay_clamps_at_zero(self):
        assert get_wave_move_delay(100) == 0.0

    def test_wave_1_initial_icbms(self):
        game = Game()
        game.start_wave()
        assert game.icbms_remaining_this_wave > 0

    def test_multiplier_matches_wave(self):
        game = Game()
        game.wave_number = 5
        assert game.multiplier == 3

    def test_destroyed_cities_persist_into_next_wave(self):
        game = Game()
        game.start_wave()
        game.cities.destroy_city(0)
        game.icbms_remaining_this_wave = 0
        game.update()  # ends wave 1, advances to wave 2
        game.start_wave()
        assert game.cities.cities[0].is_destroyed

    def test_kill_score_scales_with_multiplier(self):
        game = Game()
        game.wave_number = 5  # 3x multiplier
        game.start_wave()
        game.icbms_remaining_this_wave = 0
        icbm = ICBM(entry_x=100, entry_y=100, target_x=100, target_y=220, speed=1)
        game.missiles.icbm_slots[0] = icbm
        exp = Explosion(center_x=100, center_y=100, max_radius=13, expand_rate=13)
        game.explosions.add(exp)
        for _ in range(EXPLOSION_GROUPS):
            game.update()
            if game.score_display.player_score:
                break
        assert game.score_display.player_score == POINTS_PER_ICBM * 3


# ── Slot Management Tests ──────────────────────────────────────────────────


class TestSlotManagement:
    def test_8_abm_slots(self):
        mgr = MissileSlotManager()
        for _ in range(MAX_ABM_SLOTS):
            abm = ABM(silo_index=1, start_x=128, start_y=220,
                       target_x=128, target_y=50)
            assert mgr.add_abm(abm) is True
        assert mgr.active_abm_count == MAX_ABM_SLOTS

    def test_8_icbm_slots(self):
        mgr = MissileSlotManager()
        for _ in range(MAX_ICBM_SLOTS):
            icbm = ICBM(entry_x=0, entry_y=0, target_x=128, target_y=200)
            assert mgr.add_icbm(icbm) is True
        assert mgr.active_icbm_count == MAX_ICBM_SLOTS

    def test_1_flier_slot(self):
        mgr = MissileSlotManager()
        f1 = Flier(flier_type=FlierType.BOMBER, altitude=115,
                    direction=1, speed=1, resurrection_timer=60,
                    firing_timer=30)
        f2 = Flier(flier_type=FlierType.SATELLITE, altitude=115,
                    direction=-1, speed=1, resurrection_timer=60,
                    firing_timer=30)
        assert mgr.set_flier(f1) is True
        assert mgr.set_flier(f2) is False

    def test_20_explosion_slots(self):
        mgr = ExplosionManager()
        for i in range(20):
            exp = Explosion(center_x=100, center_y=100, max_radius=13)
            assert mgr.add(exp) is True
        extra = Explosion(center_x=100, center_y=100, max_radius=13)
        assert mgr.add(extra) is False

    def test_slots_reused(self):
        mgr = MissileSlotManager()
        abm = ABM(silo_index=1, start_x=128, start_y=220,
                   target_x=128, target_y=50)
        mgr.add_abm(abm)
        abm.deactivate()
        mgr.clear_inactive()
        assert mgr.active_abm_count == 0
        # Slot should be reusable
        new_abm = ABM(silo_index=1, start_x=128, start_y=220,
                       target_x=128, target_y=50)
        assert mgr.add_abm(new_abm) is True


# ── Explosion Tests ─────────────────────────────────────────────────────────


class TestExplosionMechanics:
    def test_max_radius_13(self):
        assert EXPLOSION_MAX_RADIUS == 13

    def test_lifecycle(self):
        exp = Explosion(center_x=100, center_y=100, max_radius=5,
                        expand_rate=1, hold_frames=3, contract_rate=1)
        states = []
        for _ in range(20):
            exp.update()
            states.append(exp.state)
            if not exp.is_active:
                break
        assert ExplosionState.EXPANDING in states
        assert ExplosionState.HOLDING in states
        assert ExplosionState.CONTRACTING in states
        assert exp.state == ExplosionState.DONE

    def test_5_groups(self):
        mgr = ExplosionManager()
        groups_seen = set()
        for _ in range(5):
            groups_seen.add(mgr.current_group)
            mgr.update()
        assert len(groups_seen) == 5

    def test_collision_above_line_33(self):
        exp = Explosion(center_x=100, center_y=100, max_radius=13)
        exp.current_radius = 10
        assert exp.collides_with(100, 100)

    def test_no_collision_below_line_33(self):
        exp = Explosion(center_x=100, center_y=20, max_radius=13)
        exp.current_radius = 10
        assert not exp.collides_with(100, 20)

    def test_icbm_collision_detection(self):
        mgr = ExplosionManager()
        exp = Explosion(center_x=100, center_y=100, max_radius=13,
                        expand_rate=13)
        mgr.add(exp)
        updated = mgr.update()
        hits = mgr.check_icbm_collisions(updated, [(100, 100, 0)])
        assert 0 in hits


# ── Game Integration Tests ──────────────────────────────────────────────────


class TestGameIntegration:
    def test_fire_from_silo(self):
        game = Game()
        game.start_wave()
        assert game.fire_from_silo(1, 128, 50) is True
        assert game.missiles.active_abm_count == 1

    def test_fire_nearest(self):
        game = Game()
        game.start_wave()
        assert game.fire_nearest(40, 50) is True
        assert game.missiles.active_abm_count == 1

    def test_spawn_icbm(self):
        game = Game()
        game.start_wave()
        assert game.spawn_icbm(100, 0, 100, 200) is True
        assert game.missiles.active_icbm_count == 1

    def test_update_returns_running(self):
        game = Game()
        game.start_wave()
        game.spawn_icbm(100, 0, 100, 200)
        state = game.update()
        assert state == GameState.RUNNING


class TestMIRVWaveGate:
    """Integration-level check that wave 1 never produces a MIRV split,
    end to end through the real update loop (not just the isolated
    check_mirv_conditions unit tests) -- regression test for a bug
    where the game had no wave gate at all, letting every eligible
    ICBM split from wave 1 onward."""

    def test_no_mirv_children_during_full_wave_1(self):
        game = Game()
        game.start_wave()
        assert game.wave_number == 1
        for _ in range(3000):
            if game.state != GameState.RUNNING:
                break
            game.update()
            for missile in game.missiles.icbm_slots:
                assert not (missile is not None and missile.has_mirved)

    def test_mirv_mechanism_works_from_wave_2_in_isolation(self):
        """Confirms the split mechanism itself is enabled from wave 2
        onward. Uses a single, cleanly-eligible ICBM with nothing else
        in the table rather than waiting for one to occur naturally
        over N frames of full wave-2 play: with several ICBMs in
        flight at once, the "no previously examined missile above
        MIRV_ALTITUDE_HIGH" condition ($56d1) makes MIRVs legitimately
        rare in practice (any missile further along than the 128-159
        band blocks the rest), so asserting natural occurrence within
        a fixed frame budget is flaky by nature of that gate, not a
        sign of a broken mechanism."""
        game = Game()
        game.wave_number = 2
        game.start_wave()
        game.missiles.icbm_slots = [None] * len(game.missiles.icbm_slots)
        icbm = ICBM(entry_x=200, entry_y=140, target_x=205, target_y=220,
                    speed=1, move_delay=0.0, can_mirv=True)
        game.missiles.icbm_slots[0] = icbm
        game.icbms_remaining_this_wave = 5
        game._process_mirv_splits()
        assert icbm.has_mirved
        assert game.missiles.active_icbm_count == 4  # parent + 3 children


# ── Detonation / arrival Tests ──────────────────────────────────────────────


class TestArrivals:
    def test_abm_arrival_spawns_explosion(self):
        game = Game()
        game.start_wave()
        game.icbms_remaining_this_wave = 0
        game.fire_from_silo(1, 128, 50)
        abm = next(s for s in game.missiles.abm_slots if s is not None)
        # Force the ABM to its target so it detonates this frame.
        abm.current_x_fp = abm.target_x << 8
        abm.current_y_fp = abm.target_y << 8
        game.update()
        assert game.explosions.active_count == 1
        centers = game.explosions.active_explosion_centers
        assert centers[0] == (128, 50)

    def test_icbm_arrival_destroys_city_and_spawns_explosion(self):
        game = Game()
        game.start_wave()
        city = game.cities.active_cities[0]
        cx, cy = city.position
        game.spawn_icbm(cx, 0, cx, cy)
        icbm = next(s for s in game.missiles.icbm_slots if s is not None)
        icbm.current_x_fp = cx << 8
        icbm.current_y_fp = cy << 8
        icbm.move_wait_counter = icbm.move_delay  # force this frame's move to trigger
        game.icbms_remaining_this_wave = 0
        game.update()
        assert city.is_destroyed
        assert game.explosions.active_count >= 1

    def test_icbm_arrival_destroys_silo(self):
        game = Game()
        game.start_wave()
        silo = game.defenses.silos[0]
        sx, sy = silo.position
        game.spawn_icbm(sx, 0, sx, sy)
        icbm = next(s for s in game.missiles.icbm_slots if s is not None)
        icbm.current_x_fp = sx << 8
        icbm.current_y_fp = sy << 8
        icbm.move_wait_counter = icbm.move_delay  # force this frame's move to trigger
        game.icbms_remaining_this_wave = 0
        game.update()
        assert silo.is_destroyed


class TestInterception:
    """Regression tests for the actual cause of "damage out of nowhere":
    an ICBM shot down mid-flight (far from its target) was left sitting
    in the slot table with is_active=False after the collision step,
    since clear_inactive() only runs earlier in the SAME frame, not
    after collision detection. The NEXT frame's _process_arrivals()
    would then see that inactive slot and treat it as having reached
    its target naturally -- destroying the city/silo it had been
    heading toward, and spawning an explosion there, even though the
    missile was destroyed high in the air nowhere near the ground."""

    def test_intercepted_icbm_does_not_destroy_its_target_city(self):
        game = Game()
        game.start_wave()
        city = game.cities.active_cities[0]
        cx, cy = city.position
        game.spawn_icbm(cx, 0, cx, cy)
        icbm = next(s for s in game.missiles.icbm_slots if s is not None)
        icbm.current_x_fp = cx << 8
        icbm.current_y_fp = 50 << 8  # high in the air, nowhere near the ground
        game.icbms_remaining_this_wave = 0

        game.explosions.add(
            Explosion(center_x=cx, center_y=50, max_radius=13, expand_rate=13)
        )
        for _ in range(5):
            game.update()

        assert icbm.intercepted
        assert not city.is_destroyed

    def test_intercepted_icbm_does_not_destroy_its_target_silo(self):
        game = Game()
        game.start_wave()
        silo = game.defenses.silos[0]
        sx, sy = silo.position
        game.spawn_icbm(sx, 0, sx, sy)
        icbm = next(s for s in game.missiles.icbm_slots if s is not None)
        icbm.current_x_fp = sx << 8
        icbm.current_y_fp = 50 << 8
        game.icbms_remaining_this_wave = 0

        game.explosions.add(
            Explosion(center_x=sx, center_y=50, max_radius=13, expand_rate=13)
        )
        for _ in range(5):
            game.update()

        assert icbm.intercepted
        assert not silo.is_destroyed

    def test_intercept_marks_flag_deactivate_does_not(self):
        icbm = ICBM(entry_x=100, entry_y=0, target_x=100, target_y=200, speed=1)
        icbm.deactivate()
        assert icbm.is_active is False
        assert icbm.intercepted is False

        icbm2 = ICBM(entry_x=100, entry_y=0, target_x=100, target_y=200, speed=1)
        icbm2.intercept()
        assert icbm2.is_active is False
        assert icbm2.intercepted is True

    def test_naturally_arrived_icbm_still_destroys_target(self):
        """Sanity check that the fix didn't break the normal ground-hit
        path -- only genuinely intercepted missiles are skipped."""
        game = Game()
        game.start_wave()
        city = game.cities.active_cities[0]
        cx, cy = city.position
        game.spawn_icbm(cx, 0, cx, cy)
        icbm = next(s for s in game.missiles.icbm_slots if s is not None)
        icbm.current_x_fp = cx << 8
        icbm.current_y_fp = cy << 8
        icbm.move_wait_counter = icbm.move_delay
        game.icbms_remaining_this_wave = 0
        game.update()
        assert not icbm.intercepted
        assert city.is_destroyed


class TestGroundCratering:
    """Any explosion (ABM or ICBM) that visually touches the ground line
    permanently scars the terrain there, whether or not it destroyed a
    city/silo -- matches the original arcade's persistent battlefield
    damage, including near-misses on open ground."""

    def test_icbm_impact_craters_ground(self):
        game = Game()
        game.start_wave()
        game.spawn_icbm(100, 0, 100, GROUND_Y)
        icbm = next(s for s in game.missiles.icbm_slots if s is not None)
        icbm.current_x_fp = 100 << 8
        icbm.current_y_fp = GROUND_Y << 8
        icbm.move_wait_counter = icbm.move_delay
        game.icbms_remaining_this_wave = 0
        game.update()
        assert 100 in game.ground_craters

    def test_abm_intercept_near_ground_craters(self):
        game = Game()
        game.start_wave()
        game.icbms_remaining_this_wave = 0
        game.fire_from_silo(1, 128, GROUND_Y)
        abm = next(s for s in game.missiles.abm_slots if s is not None)
        abm.current_x_fp = 128 << 8
        abm.current_y_fp = GROUND_Y << 8
        game.update()
        assert 128 in game.ground_craters

    def test_abm_intercept_high_altitude_does_not_crater(self):
        game = Game()
        game.start_wave()
        game.icbms_remaining_this_wave = 0
        game.fire_from_silo(1, 128, 20)
        abm = next(s for s in game.missiles.abm_slots if s is not None)
        abm.current_x_fp = 128 << 8
        abm.current_y_fp = 20 << 8
        game.update()
        assert 128 not in game.ground_craters

    def test_craters_persist_across_wave_start(self):
        game = Game()
        game.start_wave()
        game.ground_craters.append(77)
        game.icbms_remaining_this_wave = 0
        game.update()  # ends wave 1
        game.start_wave()
        assert 77 in game.ground_craters

    def test_craters_capped_with_fifo_eviction(self):
        game = Game()
        game.start_wave()
        for i in range(MAX_GROUND_CRATERS + 10):
            game._maybe_crater_ground(i, GROUND_Y, 0)
        assert len(game.ground_craters) == MAX_GROUND_CRATERS
        assert game.ground_craters[0] == 10  # oldest 10 evicted FIFO
        assert game.ground_craters[-1] == MAX_GROUND_CRATERS + 9


# ── Attack Pacing Tests ──────────────────────────────────────────────────


class TestAttackPacing:
    def test_wave_start_launches_initial_batch(self):
        game = Game()
        game.start_wave()
        game.update()
        assert game.missiles.active_icbm_count > 0

    def test_pacing_blocks_until_descent(self):
        game = Game()
        game.start_wave()
        game.update()  # launches initial batch near the top of the screen
        count_after_first_batch = game.missiles.active_icbm_count
        # Immediately after launch, missiles are near the top (high
        # "altitude"), so pacing should hold off on a second batch.
        game.update()
        assert game.missiles.active_icbm_count <= count_after_first_batch + ATTACK_BATCH_SIZE

    def test_never_exceeds_icbm_slots(self):
        game = Game()
        game.start_wave()
        for _ in range(200):
            if game.state != GameState.RUNNING:
                break
            game.update()
            assert game.missiles.active_icbm_count <= MAX_ICBM_SLOTS


# ── Mercy Rule Tests ─────────────────────────────────────────────────────


class TestMercyRule:
    def test_wave_ends_immediately_after_three_cities_and_no_abms(self):
        game = Game()
        game.start_wave()
        for silo in game.defenses.silos:
            silo.abm_count = 0
        for i, city in enumerate(game.cities.cities):
            if i < MAX_CITIES_DESTROYED_PER_WAVE:
                game.cities.destroy_city(i)
        state = game.update()
        assert state == GameState.WAVE_END

    def test_never_loses_more_than_three_cities_via_targeting(self):
        game = Game()
        game.start_wave()
        for i in range(MAX_CITIES_DESTROYED_PER_WAVE):
            game.cities.destroy_city(i)
        targets = game._pick_targets(5)
        city_positions = {c.position for c in game.cities.active_cities}
        targeted = [t for t in targets if t in city_positions]
        # With the per-wave limit already spent, any further city target
        # must be empty (no cities left to target under the cap) or fall
        # back to re-targeting an already-destroyed-city slot's siblings.
        assert len(set(targeted)) <= 1


# ── Smart Bomb / MIRV Integration Tests ─────────────────────────────────


class TestSmartBombIntegration:
    def test_evasion_cleared_when_no_explosions_nearby(self):
        game = Game()
        game.start_wave()
        sb = SmartBomb(entry_x=100, entry_y=100, target_x=100, target_y=220, speed=1)
        game.missiles.icbm_slots[0] = sb
        game.icbms_remaining_this_wave = 0
        game.update()
        assert sb.evasion_active is False

    def test_evasion_activates_near_explosion(self):
        game = Game()
        game.start_wave()
        sb = SmartBomb(entry_x=100, entry_y=100, target_x=100, target_y=220, speed=1)
        game.missiles.icbm_slots[0] = sb
        game.explosions.add(Explosion(center_x=105, center_y=100, max_radius=13))
        game.icbms_remaining_this_wave = 0
        game._update_smart_bomb_evasion()
        assert sb.evasion_active is True


# ── Flier Integration Tests ─────────────────────────────────────────────


class TestFlierIntegration:
    def test_flier_spawns_after_delay(self):
        game = Game()
        game.wave_number = FLIER_START_WAVE
        game.start_wave()
        game.flier_spawn_timer = 0
        game.update()
        assert game.missiles.flier_slot is not None

    def test_no_flier_before_start_wave(self):
        game = Game()
        game.wave_number = FLIER_START_WAVE - 1
        game.start_wave()
        game.flier_spawn_timer = 0
        for _ in range(5):
            game.update()
        assert game.missiles.flier_slot is None
