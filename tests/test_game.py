"""
Tests for main game logic and state management.

Covers game state transitions, scoring, wave management, slot management,
explosion mechanics, and wave helpers.
"""

import pytest

from src.config import (
    BONUS_CITY_POINTS,
    EXPLOSION_MAX_RADIUS,
    MAX_ABM_SLOTS,
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
    get_wave_speed,
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

    def test_wave_speed_increases(self):
        assert get_wave_speed(1) < get_wave_speed(5)

    def test_attack_pace_altitude(self):
        assert get_attack_pace_altitude(1) == 200
        assert get_attack_pace_altitude(11) == 180
        assert get_attack_pace_altitude(50) == 180  # clamped

    def test_wave_speed_clamps(self):
        assert get_wave_speed(100) == 8

    def test_wave_1_initial_icbms(self):
        game = Game()
        game.start_wave()
        assert game.icbms_remaining_this_wave > 0


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
