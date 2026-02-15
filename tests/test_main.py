"""
Tests for main.py – application initialization and argument parsing.
"""

import pytest

from main import parse_args, MissileCommandApp, FRAME_TIME, IRQ_PER_FRAME


# ── Argument parsing ───────────────────────────────────────────────────────


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.scale == 2
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
        assert app.scale == 2
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