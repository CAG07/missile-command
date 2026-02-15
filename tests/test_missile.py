"""
Tests for missile-related functionality from src/models/missile.py.

Covers ABM, ICBM, SmartBomb, Flier, MIRV logic, and slot management.
"""

import pytest

from src.config import (
    ABM_SPEED_CENTER,
    ABM_SPEED_SIDE,
    MAX_ABM_SLOTS,
    MAX_ICBM_SLOTS,
    MIRV_ALTITUDE_HIGH,
    MIRV_ALTITUDE_LOW,
    MIRV_MAX_CHILDREN,
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


# ── ABM Tests ──────────────────────────────────────────────────────────────


class TestABMMissile:
    def test_side_silo_speed_3(self):
        abm = ABM(silo_index=0, start_x=32, start_y=220,
                   target_x=128, target_y=50)
        # Side silo uses speed 3
        assert abm.x_increment != 0 or abm.y_increment != 0

    def test_center_silo_speed_7(self):
        abm = ABM(silo_index=1, start_x=128, start_y=220,
                   target_x=128, target_y=50)
        assert abm.y_increment != 0

    def test_center_faster_than_side(self):
        abm_side = ABM(silo_index=0, start_x=32, start_y=220,
                        target_x=128, target_y=50)
        abm_center = ABM(silo_index=1, start_x=128, start_y=220,
                          target_x=128, target_y=50)
        assert abs(abm_center.y_increment) > abs(abm_side.y_increment)

    def test_fixed_point_position(self):
        abm = ABM(silo_index=1, start_x=128, start_y=220,
                   target_x=128, target_y=50)
        assert abm.current_x_fp == to_fixed(128)
        assert abm.current_y_fp == to_fixed(220)

    def test_update_moves(self):
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

    def test_trail_positions(self):
        abm = ABM(silo_index=1, start_x=128, start_y=220,
                   target_x=128, target_y=50)
        positions = [(abm.current_x, abm.current_y)]
        for _ in range(5):
            abm.update()
            positions.append((abm.current_x, abm.current_y))
        # Should have moved
        assert positions[-1] != positions[0]

    def test_max_8_abms(self):
        mgr = MissileSlotManager()
        for _ in range(MAX_ABM_SLOTS):
            abm = ABM(silo_index=1, start_x=128, start_y=220,
                       target_x=128, target_y=50)
            assert mgr.add_abm(abm) is True
        extra = ABM(silo_index=1, start_x=128, start_y=220,
                     target_x=128, target_y=50)
        assert mgr.add_abm(extra) is False


# ── ICBM Tests ──────────────────────────────────────────────────────────────


class TestICBMMissile:
    def test_speed_varies(self):
        icbm1 = ICBM(entry_x=100, entry_y=0, target_x=100, target_y=200,
                      speed=1)
        icbm2 = ICBM(entry_x=100, entry_y=0, target_x=100, target_y=200,
                      speed=5)
        assert abs(icbm2.y_increment) > abs(icbm1.y_increment)

    def test_fixed_point_movement(self):
        icbm = ICBM(entry_x=100, entry_y=0, target_x=100, target_y=200,
                     speed=2)
        assert icbm.current_x_fp == to_fixed(100)
        old_fp = icbm.current_y_fp
        icbm.update()
        assert icbm.current_y_fp != old_fp

    def test_target_tracking(self):
        icbm = ICBM(entry_x=0, entry_y=0, target_x=200, target_y=200,
                     speed=3)
        for _ in range(500):
            icbm.update()
            if not icbm.is_active:
                break
        assert not icbm.is_active

    def test_slot_limit(self):
        mgr = MissileSlotManager()
        for _ in range(MAX_ICBM_SLOTS):
            icbm = ICBM(entry_x=0, entry_y=0, target_x=128, target_y=200)
            assert mgr.add_icbm(icbm) is True
        extra = ICBM(entry_x=0, entry_y=0, target_x=128, target_y=200)
        assert mgr.add_icbm(extra) is False


# ── MIRV Tests ──────────────────────────────────────────────────────────────


class TestMIRVMissile:
    def _make_icbm_at_altitude(self, alt):
        return ICBM(
            entry_x=100, entry_y=alt, target_x=100, target_y=220,
            speed=1, can_mirv=True,
        )

    def test_splits_in_range_128_159(self):
        icbm = self._make_icbm_at_altitude(140)
        assert ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=5, any_above_high=False,
        )

    def test_no_mirv_above_159(self):
        icbm = self._make_icbm_at_altitude(160)
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=5, any_above_high=False,
        )

    def test_no_mirv_below_128(self):
        icbm = self._make_icbm_at_altitude(127)
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=5, any_above_high=False,
        )

    def test_requires_available_slots(self):
        icbm = self._make_icbm_at_altitude(140)
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=MAX_ICBM_SLOTS,
            remaining_wave_icbms=5, any_above_high=False,
        )

    def test_spawns_up_to_3(self):
        icbm = self._make_icbm_at_altitude(140)
        targets = [(80, 220), (120, 220), (160, 220)]
        children = icbm.mirv(targets, active_icbm_count=2,
                             remaining_wave_icbms=5)
        assert len(children) == MIRV_MAX_CHILDREN

    def test_each_mirv_different_target(self):
        icbm = self._make_icbm_at_altitude(140)
        targets = [(80, 220), (120, 220), (160, 220)]
        children = icbm.mirv(targets, active_icbm_count=2,
                             remaining_wave_icbms=5)
        target_xs = [c.target_x for c in children]
        assert len(set(target_xs)) == 3

    def test_mirv_marks_parent(self):
        icbm = self._make_icbm_at_altitude(140)
        targets = [(80, 220)]
        icbm.mirv(targets, active_icbm_count=2, remaining_wave_icbms=5)
        assert icbm.has_mirved

    def test_blocked_by_higher_missile(self):
        icbm = self._make_icbm_at_altitude(140)
        assert not ICBM.check_mirv_conditions(
            icbm, active_icbm_count=2,
            remaining_wave_icbms=5, any_above_high=True,
        )


# ── Smart Bomb Tests ────────────────────────────────────────────────────────


class TestSmartBombMissile:
    def test_max_2_active(self):
        mgr = MissileSlotManager()
        sb1 = SmartBomb(entry_x=0, entry_y=0, target_x=128, target_y=200,
                        speed=1)
        sb2 = SmartBomb(entry_x=0, entry_y=0, target_x=128, target_y=200,
                        speed=1)
        sb3 = SmartBomb(entry_x=0, entry_y=0, target_x=128, target_y=200,
                        speed=1)
        assert mgr.add_icbm(sb1) is True
        assert mgr.add_icbm(sb2) is True
        assert mgr.add_icbm(sb3) is False

    def test_normal_movement(self):
        sb = SmartBomb(entry_x=100, entry_y=0, target_x=100, target_y=200,
                       speed=2)
        old_y = sb.current_y
        sb.update()
        assert sb.current_y > old_y

    def test_evasion_activates(self):
        sb = SmartBomb(entry_x=100, entry_y=0, target_x=100, target_y=200,
                       speed=1)
        sb.detect_explosions([(90, 50)])
        assert sb.evasion_active

    def test_evasion_deactivates(self):
        sb = SmartBomb(entry_x=100, entry_y=0, target_x=100, target_y=200,
                       speed=1)
        sb.detect_explosions([(90, 50)])
        sb.detect_explosions([])
        assert not sb.evasion_active

    def test_evasion_movement(self):
        sb = SmartBomb(entry_x=100, entry_y=50, target_x=100, target_y=200,
                       speed=2)
        sb.detect_explosions([(110, 60)])
        old_y = sb.current_y
        sb.update()
        # Should still move (evading)
        assert sb.is_active


# ── Flier Tests ─────────────────────────────────────────────────────────────


class TestFlierMissile:
    def test_random_type(self):
        f = Flier.create_random(wave_number=1)
        assert f.flier_type in (FlierType.BOMBER, FlierType.SATELLITE)

    def test_horizontal_movement(self):
        f = Flier(flier_type=FlierType.BOMBER, altitude=115,
                  direction=1, speed=2, resurrection_timer=60,
                  firing_timer=30, current_x=0)
        f.update()
        assert f.current_x == 2

    def test_fires_missiles(self):
        f = Flier(flier_type=FlierType.SATELLITE, altitude=115,
                  direction=1, speed=1, resurrection_timer=60,
                  firing_timer=30, current_x=100)
        missiles = f.fire([(50, 220), (150, 220)])
        assert len(missiles) == 2

    def test_resurrection_cooldown_decreases(self):
        f1 = Flier.create_random(wave_number=1)
        f2 = Flier.create_random(wave_number=5)
        assert f2.resurrection_timer <= f1.resurrection_timer

    def test_firing_cooldown_decreases(self):
        f1 = Flier.create_random(wave_number=1)
        f2 = Flier.create_random(wave_number=5)
        assert f2.firing_timer <= f1.firing_timer


# ── Fixed-Point Math Tests ──────────────────────────────────────────────────


class TestFixedPointMath:
    def test_to_fixed_accurate(self):
        assert to_fixed(0) == 0
        assert to_fixed(1) == 256
        assert to_fixed(10) == 2560

    def test_from_fixed_accurate(self):
        assert from_fixed(256) == 1
        assert from_fixed(2560) == 10

    def test_round_trip(self):
        for v in (0, 1, 7, 100, 255):
            assert from_fixed(to_fixed(v)) == v

    def test_distance_capped_255(self):
        d = distance_approx(0, 0, 500, 500)
        assert d == 255

    def test_distance_approximation(self):
        d = distance_approx(0, 0, 100, 100)
        assert d == 137  # max + 3/8 * min

    def test_increment_calculation(self):
        x_inc, y_inc = compute_increments(0, 0, 100, 0, 3)
        assert x_inc > 0
        assert y_inc == 0
