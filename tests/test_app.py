"""
Tests for src/app.py -- application initialization, argument parsing,
input handling, and the wave-end tally screen.
"""

import pytest

from src.app import (
    parse_args,
    MissileCommandApp,
    FRAME_TIME,
    IRQ_PER_FRAME,
    TALLY_TICK_INTERVAL_FRAMES,
)
from src.config import SCREEN_WIDTH, SCREEN_HEIGHT, WAVE_END_DISPLAY_FRAMES
from src.game import GameState


# ── Argument parsing ───────────────────────────────────────────────────────


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.scale == 3
        assert args.fullscreen is False
        assert args.debug is False
        assert args.wave == 1
        assert args.marathon is True
        assert args.tournament is False

    def test_fullscreen_flag(self):
        args = parse_args(["--fullscreen"])
        assert args.fullscreen is True

    def test_scale_multiplier(self):
        for n in range(1, 5):
            args = parse_args(["--scale", str(n)])
            assert args.scale == n

    def test_invalid_scale_rejected(self):
        with pytest.raises(SystemExit):
            parse_args(["--scale", "5"])

    def test_debug_flag(self):
        args = parse_args(["--debug"])
        assert args.debug is True

    def test_attract_flag(self):
        args = parse_args(["--attract"])
        assert args.attract is True

    def test_wave_number(self):
        args = parse_args(["--wave", "5"])
        assert args.wave == 5

    def test_tournament_mode(self):
        args = parse_args(["--tournament"])
        assert args.tournament is True

    def test_marathon_tournament_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            parse_args(["--marathon", "--tournament"])


# ── MissileCommandApp (without pygame) ──────────────────────────────────────


class TestMissileCommandApp:
    def test_app_defaults(self):
        app = MissileCommandApp()
        assert app.scale == 3
        assert app.fullscreen is False
        assert app.debug is False
        assert app.running is False

    def test_frame_time_constant(self):
        assert abs(FRAME_TIME - 1.0 / 60) < 1e-6

    def test_irq_per_frame(self):
        assert IRQ_PER_FRAME == 4

    def test_irq_simulation(self):
        app = MissileCommandApp()
        app.running = True
        old_irq = app.irq_counter
        app._simulate_irqs()
        assert app.irq_counter == old_irq + IRQ_PER_FRAME

    def test_color_cycle_counter_wraps(self):
        app = MissileCommandApp()
        app.running = True
        app.color_cycle_counter = 7
        app._simulate_irqs()
        # After 4 IRQs from counter=7: 8→reset, 9→1, 10→2, 11→3
        # Actually: 7+1=8→reset to 0, 0+1=1, 1+1=2, 2+1=3
        assert app.color_cycle_counter == 3

    def test_defer_score_redraw_default(self):
        app = MissileCommandApp()
        assert app.defer_score_redraw is False

    def test_tournament_disables_bonus(self):
        app = MissileCommandApp(tournament=True)
        app.game.cities.bonus_threshold = 0
        assert app.game.cities.bonus_threshold == 0


# ── Silo firing and keyboard controls (without pygame display) ──────────────


class TestSiloFiring:
    """Tests that the app correctly maps silo indices to game.fire_from_silo."""

    def test_fire_silo_left(self):
        app = MissileCommandApp()
        app.game.start_wave()
        app._fire_silo(0)
        assert app.game.missiles.active_abm_count == 1

    def test_fire_silo_center(self):
        app = MissileCommandApp()
        app.game.start_wave()
        app._fire_silo(1)
        assert app.game.missiles.active_abm_count == 1

    def test_fire_silo_right(self):
        app = MissileCommandApp()
        app.game.start_wave()
        app._fire_silo(2)
        assert app.game.missiles.active_abm_count == 1

    def test_fire_silo_noop_in_attract_mode(self):
        app = MissileCommandApp()
        # game starts in ATTRACT, firing should be a no-op
        app._fire_silo(1)
        assert app.game.missiles.active_abm_count == 0

    def test_fire_all_three_silos(self):
        app = MissileCommandApp()
        app.game.start_wave()
        app._fire_silo(0)
        app._fire_silo(1)
        app._fire_silo(2)
        assert app.game.missiles.active_abm_count == 3

    def test_get_target_returns_tuple(self):
        app = MissileCommandApp()
        target = app._get_target()
        assert isinstance(target, tuple)
        assert len(target) == 2


class TestThreeSiloConfig:
    """Tests that the src model always initializes 3 silos."""

    def test_game_has_three_silos(self):
        from src.game import Game
        game = Game()
        assert len(game.defenses.silos) == 3

    def test_silos_at_correct_positions(self):
        from src.game import Game
        game = Game()
        assert game.defenses.silos[0].position_x == 32    # left
        assert game.defenses.silos[1].position_x == 128   # center
        assert game.defenses.silos[2].position_x == 224   # right

    def test_each_silo_starts_with_10_abms(self):
        from src.game import Game
        game = Game()
        for silo in game.defenses.silos:
            assert silo.abm_count == 10

    def test_fire_from_each_silo(self):
        from src.game import Game
        game = Game()
        game.start_wave()
        assert game.fire_from_silo(0, 100, 50) is True  # left
        assert game.fire_from_silo(1, 128, 50) is True  # center
        assert game.fire_from_silo(2, 200, 50) is True  # right
        assert game.missiles.active_abm_count == 3


# ── Crosshair / mouse controls ────────────────────────────────────────


class TestCrosshair:
    """Tests that crosshair position tracking works."""

    def test_initial_crosshair_position(self):
        app = MissileCommandApp()
        assert app.crosshair_x == SCREEN_WIDTH // 2
        assert app.crosshair_y == SCREEN_HEIGHT // 2

    def test_get_target_returns_crosshair_position(self):
        app = MissileCommandApp()
        app.crosshair_x = 50
        app.crosshair_y = 80
        assert app._get_target() == (50, 80)

    def test_fire_uses_crosshair_position(self):
        app = MissileCommandApp()
        app.game.start_wave()
        app.crosshair_x = 100
        app.crosshair_y = 50
        app._fire_silo(1)
        assert app.game.missiles.active_abm_count == 1


# ── Wave-end tally screen ────────────────────────────────────────────────


class TestTallyScreen:
    """Tests for the count-up tally shown between waves."""

    def test_displayed_score_before_any_wave_end(self):
        app = MissileCommandApp()
        assert app.tally_displayed_score == app.game.score_display.player_score

    def test_ticks_total_set_on_wave_end_transition(self):
        app = MissileCommandApp()
        app.game.start_wave()
        app.game.icbms_remaining_this_wave = 0
        app._update()  # RUNNING -> WAVE_END
        expected = (
            app.game.last_wave_surviving_cities + app.game.last_wave_remaining_abms
        )
        assert app.tally_ticks_total == expected
        assert app.tally_ticks_done == 0

    def test_ticks_progress_and_score_counts_up(self):
        app = MissileCommandApp()
        app.game.start_wave()
        app.game.icbms_remaining_this_wave = 0
        app._update()  # RUNNING -> WAVE_END
        start_score = app.tally_displayed_score
        for _ in range(app.tally_ticks_total * TALLY_TICK_INTERVAL_FRAMES):
            app._update()
        assert app.tally_ticks_done == app.tally_ticks_total
        assert app.tally_displayed_score == app.game.score_display.player_score
        assert app.tally_displayed_score >= start_score

    def test_advances_to_next_wave_after_display_timer(self):
        app = MissileCommandApp()
        app.game.start_wave()
        wave_before = app.game.wave_number
        app.game.icbms_remaining_this_wave = 0
        app._update()  # RUNNING -> WAVE_END; wave_number already incremented
        assert app.game.wave_number == wave_before + 1
        for _ in range(WAVE_END_DISPLAY_FRAMES + 1):
            app._update()
        # start_wave() fires once the tally timer expires, re-entering
        # RUNNING for the same (already incremented) wave number.
        assert app.game.wave_number == wave_before + 1
        assert app.game.state == GameState.RUNNING


# ── Attract-mode autoplay demo wiring ────────────────────────────────────


class TestAttractModeWiring:
    def test_update_drives_demo_while_in_attract(self):
        app = MissileCommandApp()
        assert app.game.state == GameState.ATTRACT
        before = app.attract_demo.game.frame_count
        app._update()
        assert app.attract_demo.game.frame_count == before + 1

    def test_update_does_not_touch_idle_game_while_in_attract(self):
        app = MissileCommandApp()
        app._update()
        assert app.game.frame_count == 0

    def test_start_game_from_attract_leaves_demo_untouched(self):
        app = MissileCommandApp()
        demo_score_before = app.attract_demo.game.score_display.player_score
        app._start_game_from_attract()
        assert app.game.state == GameState.RUNNING
        assert app.attract_demo.game.score_display.player_score == demo_score_before

    def test_reset_to_attract_restarts_demo(self):
        app = MissileCommandApp()
        app.attract_demo.game.score_display.add(999)
        app._reset_to_attract()
        assert app.attract_demo.game.score_display.player_score == 0
        assert app.attract_demo.game.state == GameState.RUNNING
