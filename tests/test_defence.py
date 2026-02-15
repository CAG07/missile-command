"""
Tests for defence silo and city functionality.

Covers DefenceSilo, DefenceManager, City, CityManager, and bonus city logic.
"""

import pytest

from src.config import (
    BONUS_CITY_POINTS,
    MAX_ABM_SLOTS,
    MAX_CITIES_DESTROYED_PER_WAVE,
    NUM_CITIES_DEFAULT,
    SILO_CAPACITY,
)
from src.models.city import City, CityManager
from src.models.defence import DefenceManager, DefenceSilo


# ── Defence Silo Tests ──────────────────────────────────────────────────────


class TestDefenceSiloUnit:
    def test_three_silos_initialized(self):
        mgr = DefenceManager()
        assert len(mgr.silos) == 3

    def test_each_silo_has_10_abms(self):
        mgr = DefenceManager()
        for silo in mgr.silos:
            assert silo.abm_count == SILO_CAPACITY

    def test_silos_restored_at_wave_start(self):
        mgr = DefenceManager()
        mgr.silos[0].fire(100, 50)
        mgr.silos[1].destroy()
        mgr.restore_all()
        for silo in mgr.silos:
            assert silo.abm_count == SILO_CAPACITY
            assert not silo.is_destroyed

    def test_refuses_fire_when_8_abms_active(self):
        mgr = DefenceManager()
        assert mgr.fire(1, 100, 50, MAX_ABM_SLOTS) is None

    def test_silo_positions_match_config(self):
        mgr = DefenceManager()
        assert mgr.silos[0].position_x == 32
        assert mgr.silos[1].position_x == 128
        assert mgr.silos[2].position_x == 224

    def test_destroyed_silos_dont_fire(self):
        silo = DefenceSilo(silo_index=0, position_x=32, position_y=220)
        silo.destroy()
        assert silo.fire(100, 50) is None

    def test_fire_decrements_abm_count(self):
        silo = DefenceSilo(silo_index=1, position_x=128, position_y=220)
        silo.fire(100, 50)
        assert silo.abm_count == SILO_CAPACITY - 1

    def test_fire_empty_returns_none(self):
        silo = DefenceSilo(silo_index=0, position_x=32, position_y=220,
                           abm_count=0)
        assert silo.fire(100, 50) is None

    def test_restore(self):
        silo = DefenceSilo(silo_index=0, position_x=32, position_y=220,
                           abm_count=0)
        silo.destroy()
        silo.restore()
        assert silo.abm_count == SILO_CAPACITY
        assert not silo.is_destroyed

    def test_fire_nearest(self):
        mgr = DefenceManager()
        abm = mgr.fire_nearest(40, 50, 0)
        assert abm is not None
        assert abm.silo_index == 0  # left silo nearest to x=40

    def test_total_abm_count(self):
        mgr = DefenceManager()
        assert mgr.total_abm_count == SILO_CAPACITY * 3


# ── City Tests ──────────────────────────────────────────────────────────────


class TestCityUnit:
    def test_initial_city_count(self):
        mgr = CityManager()
        assert mgr.active_count == NUM_CITIES_DEFAULT

    def test_default_6_cities_marathon(self):
        mgr = CityManager()
        assert mgr.active_count == 6

    def test_cities_restored_at_wave_start(self):
        mgr = CityManager()
        mgr.destroy_city(0)
        mgr.destroy_city(1)
        mgr.start_wave()
        assert mgr.active_count == 6
        assert mgr.cities_destroyed_this_wave == 0

    def test_destruction_limited_to_3(self):
        mgr = CityManager()
        destroyed = 0
        for i in range(6):
            if mgr.destroy_city(i):
                destroyed += 1
        assert destroyed == MAX_CITIES_DESTROYED_PER_WAVE

    def test_destroy_and_restore(self):
        c = City(position_x=48, position_y=216)
        assert not c.is_destroyed
        c.destroy()
        assert c.is_destroyed
        c.restore()
        assert not c.is_destroyed

    def test_replace_random_crater(self):
        mgr = CityManager()
        mgr.destroy_city(0)
        mgr.bonus_cities = 1
        assert mgr.replace_random_crater() is True
        assert mgr.active_count == 6
        assert mgr.bonus_cities == 0


# ── Bonus City Tests ────────────────────────────────────────────────────────


class TestBonusCityUnit:
    def test_awarded_at_threshold(self):
        mgr = CityManager()
        mgr.bonus_threshold = 10000
        awarded = mgr.check_bonus(10000)
        assert awarded == 1
        assert mgr.bonus_cities == 1

    def test_multiple_in_single_wave(self):
        mgr = CityManager()
        mgr.bonus_threshold = 1000
        awarded = mgr.check_bonus(3000)
        assert awarded == 3
        assert mgr.bonus_cities == 3

    def test_8bit_overflow(self):
        mgr = CityManager()
        mgr.bonus_threshold = 1
        mgr.check_bonus(256)
        assert mgr.bonus_cities == 0  # 256 & 0xFF == 0

    def test_total_includes_bonus(self):
        mgr = CityManager()
        mgr.bonus_cities = 5
        assert mgr.total_cities == mgr.active_count + 5

    def test_random_replacement_position(self):
        mgr = CityManager()
        mgr.destroy_city(0)
        mgr.destroy_city(1)
        mgr.destroy_city(2)
        mgr.bonus_cities = 1
        mgr.replace_random_crater()
        # One of the destroyed cities should be restored
        restored = sum(1 for c in mgr.cities[:3] if not c.is_destroyed)
        assert restored == 1


# ── Wave Limitation Tests ───────────────────────────────────────────────────


class TestWaveLimitations:
    def test_never_lose_more_than_3(self):
        mgr = CityManager()
        destroyed = 0
        for i in range(6):
            if mgr.destroy_city(i):
                destroyed += 1
        assert destroyed <= MAX_CITIES_DESTROYED_PER_WAVE

    def test_all_destroyed_property(self):
        mgr = CityManager()
        for city in mgr.cities:
            city.destroy()
        mgr.bonus_cities = 0
        assert mgr.all_destroyed is True

    def test_not_all_destroyed_with_bonus(self):
        mgr = CityManager()
        for city in mgr.cities:
            city.destroy()
        mgr.bonus_cities = 1
        assert mgr.all_destroyed is False
