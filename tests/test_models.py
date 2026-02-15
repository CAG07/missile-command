"""
Unit tests for Missile Command arcade-faithful models.

Covers critical calculations: fixed-point math, distance approximation,
MIRV logic, slot limits, octagonal explosions, city destruction limits,
silo capacity, and score tracking.
"""

import pytest

from src.config import (
    ABM_SPEED_CENTER,
    ABM_SPEED_SIDE,
    BONUS_CITY_POINTS,
    EXPLOSION_MAX_RADIUS,
    MAX_ABM_SLOTS,
    MAX_CITIES_DESTROYED_PER_WAVE,
    MAX_ICBM_SLOTS,
    MIRV_ALTITUDE_HIGH,
    MIRV_ALTITUDE_LOW,
    SILO_CAPACITY,
)
from src.models.missile import (
    ABM,
    ICBM,
    Flier,
    FlierType,
    MissileSlotManager,
    SmartBomb,
    compute_increments,
    distance_approx,
    from_fixed,
    has_passed_target,
    to_fixed,
)
from src.models.explosion import (
    Explosion,
    ExplosionManager,
    ExplosionState,
    octagon_points,
    point_in_octagon,
)
from src.models.city import City, CityManager
from src.models.defence import DefenceManager, DefenceSilo
from src.game import Game, GameState
from src.ui.text import ScoreDisplay
from src.utils.functions import (
    calculate_wave_bonus,
    get_attack_pace_altitude,
    get_wave_speed,
)


# ── Fixed-point math ───────────────────────────────────────────────────────


class TestFixedPoint:
    def test_to_fixed_zero(self):
        assert to_fixed(0) == 0

    def test_to_fixed_positive(self):
        assert to_fixed(1) == 256
        assert to_fixed(10) == 2560

    def test_from_fixed_round_trip(self):
        for v in (0, 1, 7, 100, 255):
            assert from_fixed(to_fixed(v)) == v

    def test_from_fixed_truncates(self):
        # 256 + 128 => integer part 1, fractional 0.5 => truncates to 1
        assert from_fixed(256 + 128) == 1


# ── Distance approximation ─────────────────────────────────────────────────


class TestDistance:
    def test_same_point(self):
        assert distance_approx(10, 20, 10, 20) == 0

    def test_horizontal(self):
        assert distance_approx(0, 0, 100, 0) == 100

    def test_vertical(self):
        assert distance_approx(0, 0, 0, 100) == 100

    def test_diagonal_approximation(self):
        # 45-degree: dx=dy=100 → max=100, min=100 → 100+37=137
        d = distance_approx(0, 0, 100, 100)
        assert d == 137

    def test_capped_at_255(self):
        d = distance_approx(0, 0, 500, 500)
        assert d == 255

    def test_symmetry(self):
        assert distance_approx(10, 20, 50, 80) == distance_approx(50, 80, 10, 20)


# ── Increment calculation ──────────────────────────────────────────────────


class TestIncrements:
    def test_zero_distance(self):
        assert compute_increments(5, 5, 5, 5, 3) == (0, 0)

    def test_horizontal_movement(self):
        x_inc, y_inc = compute_increments(0, 100, 100, 100, 3)
        assert x_inc > 0
        assert y_inc == 0

    def test_vertical_movement(self):
        x_inc, y_inc = compute_increments(100, 0, 100, 100, 3)
        assert x_inc == 0
        assert y_inc > 0


# ── has_passed_target ──────────────────────────────────────────────────────


class TestPassedTarget:
    def test_not_passed_yet(self):
        assert not has_passed_target(0, 0, 100, 100, 1, 1)

    def test_passed_x(self):
        assert has_passed_target(101, 50, 100, 100, 1, 1)

    def test_passed_y(self):
        assert has_passed_target(50, 101, 100, 100, 1, 1)

    def test_negative_direction(self):
        assert has_passed_target(99, 50, 100, 100, -1, -1)


# ── ABM ─────────────────────────────────────────────────────────────────────


class TestABM:
    def test_center_silo_speed(self):
        abm = ABM(silo_index=1, start_x=128, start_y=220,
                   target_x=128, target_y=50)
        # Center silo uses speed 7 → larger increments
        assert abm.y_increment != 0

    def test_side_silo_slower(self):
        abm_side = ABM(silo_index=0, start_x=32, start_y=220,
                        target_x=128, target_y=50)
        abm_center = ABM(silo_index=1, start_x=128, start_y=220,
                          target_x=128, target_y=50)
        # Center increment magnitude should be larger
        assert abs(abm_center.y_increment) > abs(abm_side.y_increment)

    def test_update_moves_missile(self):
        abm = ABM(silo_index=1, start_x=128, start_y=220,
                   target_x=128, target_y=50)
        old_y = abm.current_y
        abm.update()
        assert abm.current_y != old_y

    def test_deactivates_at_target(self):
        abm = ABM(silo_index=1, start_x=128, start_y=220,
                   target_x=128, target_y=210)
        for _ in range(300):
            abm.update()
            if not abm.is_active:
                break
        assert not abm.is_active


# ── ICBM ────────────────────────────────────────────────────────────────────


class TestICBM:
    def test_basic_movement(self):
        icbm = ICBM(entry_x=100, entry_y=0, target_x=100, target_y=200,
                     speed=2)
        old_y = icbm.current_y
        icbm.update()
        assert icbm.current_y > old_y

    def test_altitude_property(self):
        icbm = ICBM(entry_x=50, entry_y=10, target_x=50, target_y=200,
                     speed=1)
        assert icbm.altitude == 10

    def test_deactivates_at_target(self):
        icbm = ICBM(entry_x=128, entry_y=0, target_x=128, target_y=50,
                     speed=5)
        for _ in range(500):
            icbm.update()
            if not icbm.is_active:
                break
        assert not icbm.is_active


# ── MIRV logic ──────────────────────────────────────────────────────────────


class TestMIRV:
    def _make_icbm_at_altitude(self, alt):
        """Create an ICBM currently at altitude *alt*."""
        icbm = ICBM(
            entry_x=100, entry_y=alt, target_x=100, target_y=220,
            speed=1, can_mirv=True,
        )
        return icbm

    def test_mirv_in_range(self):
        icbm = self._make_icbm_at_altitude(140)  # in [128, 159]
        assert ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=5, any_above_high=False,
        )

    def test_mirv_below_range(self):
        icbm = self._make_icbm_at_altitude(127)
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=5, any_above_high=False,
        )

    def test_mirv_above_range(self):
        icbm = self._make_icbm_at_altitude(160)
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=5, any_above_high=False,
        )

    def test_mirv_slots_full(self):
        icbm = self._make_icbm_at_altitude(140)
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=MAX_ICBM_SLOTS,
            remaining_wave_icbms=5, any_above_high=False,
        )

    def test_mirv_no_remaining(self):
        icbm = self._make_icbm_at_altitude(140)
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=0, any_above_high=False,
        )

    def test_mirv_blocked_by_higher_missile(self):
        icbm = self._make_icbm_at_altitude(140)
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=5, any_above_high=True,
        )

    def test_mirv_already_done(self):
        icbm = self._make_icbm_at_altitude(140)
        icbm.has_mirved = True
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=5, any_above_high=False,
        )

    def test_mirv_creates_children(self):
        icbm = self._make_icbm_at_altitude(140)
        targets = [(80, 220), (120, 220), (160, 220)]
        children = icbm.mirv(targets, active_icbm_count=2,
                             remaining_wave_icbms=5)
        assert len(children) == 3
        assert icbm.has_mirved

    def test_mirv_limited_by_slots(self):
        icbm = self._make_icbm_at_altitude(140)
        targets = [(80, 220), (120, 220), (160, 220)]
        children = icbm.mirv(targets, active_icbm_count=7,
                             remaining_wave_icbms=5)
        assert len(children) == 1  # only 1 slot free


# ── SmartBomb ───────────────────────────────────────────────────────────────


class TestSmartBomb:
    def test_evasion_activates(self):
        sb = SmartBomb(
            entry_x=100, entry_y=0, target_x=100, target_y=200, speed=1,
        )
        sb.detect_explosions([(90, 50)])
        assert sb.evasion_active

    def test_evasion_deactivates(self):
        sb = SmartBomb(
            entry_x=100, entry_y=0, target_x=100, target_y=200, speed=1,
        )
        sb.detect_explosions([])
        assert not sb.evasion_active

    def test_update_moves_when_not_evading(self):
        sb = SmartBomb(
            entry_x=100, entry_y=0, target_x=100, target_y=200, speed=2,
        )
        old_y = sb.current_y
        sb.update()
        assert sb.current_y > old_y


# ── Slot Manager ────────────────────────────────────────────────────────────


class TestSlotManager:
    def test_abm_limit(self):
        mgr = MissileSlotManager()
        for i in range(MAX_ABM_SLOTS):
            abm = ABM(silo_index=1, start_x=128, start_y=220,
                       target_x=128, target_y=50)
            assert mgr.add_abm(abm) is True
        extra = ABM(silo_index=1, start_x=128, start_y=220,
                     target_x=128, target_y=50)
        assert mgr.add_abm(extra) is False

    def test_icbm_limit(self):
        mgr = MissileSlotManager()
        for _ in range(MAX_ICBM_SLOTS):
            icbm = ICBM(entry_x=0, entry_y=0, target_x=128, target_y=200)
            assert mgr.add_icbm(icbm) is True
        extra = ICBM(entry_x=0, entry_y=0, target_x=128, target_y=200)
        assert mgr.add_icbm(extra) is False

    def test_smart_bomb_limit(self):
        mgr = MissileSlotManager()
        sb1 = SmartBomb(entry_x=0, entry_y=0, target_x=128, target_y=200, speed=1)
        sb2 = SmartBomb(entry_x=0, entry_y=0, target_x=128, target_y=200, speed=1)
        sb3 = SmartBomb(entry_x=0, entry_y=0, target_x=128, target_y=200, speed=1)
        assert mgr.add_icbm(sb1) is True
        assert mgr.add_icbm(sb2) is True
        assert mgr.add_icbm(sb3) is False  # max 2 smart bombs

    def test_flier_single(self):
        mgr = MissileSlotManager()
        f1 = Flier(flier_type=FlierType.BOMBER, altitude=115,
                    direction=1, speed=1, resurrection_timer=60,
                    firing_timer=30)
        f2 = Flier(flier_type=FlierType.SATELLITE, altitude=115,
                    direction=-1, speed=1, resurrection_timer=60,
                    firing_timer=30)
        assert mgr.set_flier(f1) is True
        assert mgr.set_flier(f2) is False  # slot occupied

    def test_clear_inactive(self):
        mgr = MissileSlotManager()
        abm = ABM(silo_index=1, start_x=128, start_y=220,
                   target_x=128, target_y=50)
        mgr.add_abm(abm)
        assert mgr.active_abm_count == 1
        abm.deactivate()
        mgr.clear_inactive()
        assert mgr.active_abm_count == 0

    def test_reset_clears_all(self):
        mgr = MissileSlotManager()
        mgr.add_abm(ABM(silo_index=0, start_x=32, start_y=220,
                          target_x=128, target_y=50))
        mgr.add_icbm(ICBM(entry_x=0, entry_y=0, target_x=128, target_y=200))
        mgr.reset()
        assert mgr.active_abm_count == 0
        assert mgr.active_icbm_count == 0


# ── Explosion ───────────────────────────────────────────────────────────────


class TestExplosion:
    def test_octagon_points_count(self):
        pts = octagon_points(100, 100, 13)
        assert len(pts) == 8

    def test_octagon_shape_squarish(self):
        pts = octagon_points(100, 100, 13)
        # Top vertex should be directly above center
        assert pts[0] == (100, 87)
        # Right vertex should be directly right
        assert pts[2] == (113, 100)

    def test_point_in_octagon_center(self):
        assert point_in_octagon(100, 100, 100, 100, 13)

    def test_point_outside_octagon(self):
        assert not point_in_octagon(200, 200, 100, 100, 13)

    def test_explosion_lifecycle(self):
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
        assert not exp.is_active

    def test_collision_above_min_altitude(self):
        exp = Explosion(center_x=100, center_y=100, max_radius=13)
        exp.current_radius = 10
        assert exp.collides_with(100, 100)

    def test_no_collision_below_altitude_33(self):
        exp = Explosion(center_x=100, center_y=20, max_radius=13)
        exp.current_radius = 10
        assert not exp.collides_with(100, 20)


# ── Explosion Manager ──────────────────────────────────────────────────────


class TestExplosionManager:
    def test_add_and_update(self):
        mgr = ExplosionManager()
        exp = Explosion(center_x=100, center_y=100, max_radius=5,
                        expand_rate=1, hold_frames=2, contract_rate=1)
        assert mgr.add(exp) is True
        assert mgr.active_count == 1
        # First update processes group 0 (where the explosion was placed)
        updated = mgr.update()
        assert len(updated) >= 1

    def test_group_cycling(self):
        mgr = ExplosionManager()
        groups_seen = set()
        for _ in range(5):
            groups_seen.add(mgr.current_group)
            mgr.update()
        assert len(groups_seen) == 5

    def test_icbm_collision_detection(self):
        mgr = ExplosionManager()
        exp = Explosion(center_x=100, center_y=100, max_radius=13,
                        expand_rate=13)
        mgr.add(exp)
        # Force first update so radius is set
        updated = mgr.update()
        # ICBM at center of explosion
        hits = mgr.check_icbm_collisions(updated, [(100, 100, 0)])
        assert 0 in hits


# ── City ────────────────────────────────────────────────────────────────────


class TestCity:
    def test_destroy_and_restore(self):
        c = City(position_x=48, position_y=216)
        assert not c.is_destroyed
        c.destroy()
        assert c.is_destroyed
        c.restore()
        assert not c.is_destroyed


class TestCityManager:
    def test_default_city_count(self):
        mgr = CityManager()
        assert mgr.active_count == 6

    def test_three_per_wave_limit(self):
        mgr = CityManager()
        destroyed = 0
        for i in range(6):
            if mgr.destroy_city(i):
                destroyed += 1
        assert destroyed == MAX_CITIES_DESTROYED_PER_WAVE

    def test_start_wave_restores(self):
        mgr = CityManager()
        mgr.destroy_city(0)
        mgr.destroy_city(1)
        mgr.start_wave()
        assert mgr.active_count == 6
        assert mgr.cities_destroyed_this_wave == 0

    def test_bonus_city_award(self):
        mgr = CityManager()
        mgr.bonus_threshold = 1000
        awarded = mgr.check_bonus(3000)
        assert awarded == 3
        assert mgr.bonus_cities == 3

    def test_bonus_city_overflow(self):
        mgr = CityManager()
        mgr.bonus_threshold = 1
        mgr.check_bonus(256)
        assert mgr.bonus_cities == 0  # 256 & 0xFF == 0

    def test_replace_random_crater(self):
        mgr = CityManager()
        mgr.destroy_city(0)
        mgr.bonus_cities = 1
        assert mgr.replace_random_crater() is True
        assert mgr.active_count == 6
        assert mgr.bonus_cities == 0


# ── Defence ─────────────────────────────────────────────────────────────────


class TestDefenceSilo:
    def test_initial_capacity(self):
        silo = DefenceSilo(silo_index=0, position_x=32, position_y=220)
        assert silo.abm_count == SILO_CAPACITY

    def test_fire_decrements(self):
        silo = DefenceSilo(silo_index=1, position_x=128, position_y=220)
        abm = silo.fire(100, 50)
        assert abm is not None
        assert silo.abm_count == SILO_CAPACITY - 1

    def test_fire_empty_returns_none(self):
        silo = DefenceSilo(silo_index=0, position_x=32, position_y=220,
                           abm_count=0)
        assert silo.fire(100, 50) is None

    def test_destroyed_cannot_fire(self):
        silo = DefenceSilo(silo_index=0, position_x=32, position_y=220)
        silo.destroy()
        assert silo.fire(100, 50) is None

    def test_restore(self):
        silo = DefenceSilo(silo_index=0, position_x=32, position_y=220,
                           abm_count=0)
        silo.destroy()
        silo.restore()
        assert silo.abm_count == SILO_CAPACITY
        assert not silo.is_destroyed


class TestDefenceManager:
    def test_three_silos(self):
        mgr = DefenceManager()
        assert len(mgr.silos) == 3

    def test_fire_respects_abm_limit(self):
        mgr = DefenceManager()
        assert mgr.fire(1, 100, 50, MAX_ABM_SLOTS) is None

    def test_fire_nearest(self):
        mgr = DefenceManager()
        abm = mgr.fire_nearest(40, 50, 0)
        assert abm is not None
        assert abm.silo_index == 0  # left silo is nearest to x=40

    def test_total_abm_count(self):
        mgr = DefenceManager()
        assert mgr.total_abm_count == SILO_CAPACITY * 3

    def test_restore_all(self):
        mgr = DefenceManager()
        mgr.silos[0].fire(100, 50)
        mgr.silos[1].destroy()
        mgr.restore_all()
        assert mgr.total_abm_count == SILO_CAPACITY * 3
        assert not mgr.silos[1].is_destroyed


# ── Score Display ───────────────────────────────────────────────────────────


class TestScoreDisplay:
    def test_add_points(self):
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


# ── Wave helpers ────────────────────────────────────────────────────────────


class TestWaveHelpers:
    def test_get_wave_speed_wave1(self):
        assert get_wave_speed(1) == 1

    def test_get_wave_speed_clamps(self):
        # Beyond table length should return last entry
        assert get_wave_speed(100) == 8

    def test_attack_pace_altitude(self):
        assert get_attack_pace_altitude(1) == 200
        assert get_attack_pace_altitude(11) == 180
        assert get_attack_pace_altitude(50) == 180  # clamped

    def test_calculate_wave_bonus(self):
        bonus = calculate_wave_bonus(surviving_cities=4, remaining_abms=10)
        assert bonus == 4 * 100 + 10 * 5  # 450


# ── Game integration ────────────────────────────────────────────────────────


class TestGame:
    def test_initial_state(self):
        game = Game()
        assert game.state == GameState.ATTRACT

    def test_start_wave(self):
        game = Game()
        game.start_wave()
        assert game.state == GameState.RUNNING

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

    def test_game_over_when_all_cities_destroyed(self):
        game = Game()
        game.start_wave()
        # Destroy all cities (bypass limit for testing)
        for city in game.cities.cities:
            city.destroy()
        game.cities.bonus_cities = 0
        state = game.update()
        assert state == GameState.GAME_OVER


# ── Flier ───────────────────────────────────────────────────────────────────


class TestFlier:
    def test_create_random(self):
        f = Flier.create_random(wave_number=1)
        assert f.is_active
        assert f.flier_type in (FlierType.BOMBER, FlierType.SATELLITE)

    def test_horizontal_movement(self):
        f = Flier(flier_type=FlierType.BOMBER, altitude=115,
                  direction=1, speed=2, resurrection_timer=60,
                  firing_timer=30, current_x=0)
        f.update()
        assert f.current_x == 2

    def test_fire(self):
        f = Flier(flier_type=FlierType.SATELLITE, altitude=115,
                  direction=1, speed=1, resurrection_timer=60,
                  firing_timer=30, current_x=100)
        missiles = f.fire([(50, 220), (150, 220)])
        assert len(missiles) == 2
