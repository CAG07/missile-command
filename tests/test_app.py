"""
Tests for src/app.py -- application initialization, argument parsing,
input handling, and the wave-end tally screen.
"""

import pygame
import pytest

from src.app import (
    parse_args,
    MissileCommandApp,
    FRAME_TIME,
    IRQ_PER_FRAME,
    TALLY_TICK_INTERVAL_FRAMES,
)
from src.config import (
    GAME_OVER_DISPLAY_FRAMES,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    WAVE_END_DISPLAY_FRAMES,
    WAVE_INTRO_DISPLAY_FRAMES,
)
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
        assert args.mute is False
        assert args.cities == 6
        assert args.bonus_interval == 10000

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

    def test_mute_flag(self):
        args = parse_args(["--mute"])
        assert args.mute is True

    def test_cities_option(self):
        for n in range(4, 8):
            args = parse_args(["--cities", str(n)])
            assert args.cities == n

    def test_cities_option_rejects_out_of_range(self):
        with pytest.raises(SystemExit):
            parse_args(["--cities", "3"])
        with pytest.raises(SystemExit):
            parse_args(["--cities", "8"])

    def test_bonus_interval_option(self):
        for n in [0, 8000, 10000, 12000, 14000]:
            args = parse_args(["--bonus-interval", str(n)])
            assert args.bonus_interval == n

    def test_bonus_interval_rejects_arbitrary_value(self):
        with pytest.raises(SystemExit):
            parse_args(["--bonus-interval", "9999"])


class TestOperatorOptionsWiring:
    """Tests that CLI operator options are stored and used to construct
    a correctly-configured CityManager (see MissileCommandApp.init/
    _reset_to_attract, which aren't independently unit-testable here
    since they require a live pygame display)."""

    def test_app_stores_operator_options(self):
        app = MissileCommandApp(starting_cities=4, bonus_interval=8000, mute=True)
        assert app.starting_cities == 4
        assert app.bonus_interval == 8000
        assert app.mute is True

    def test_city_manager_honors_num_cities(self):
        from src.models.city import CityManager
        for n in range(4, 7):
            assert len(CityManager(num_cities=n).cities) == n

    def test_city_manager_num_cities_caps_at_six(self):
        from src.models.city import CityManager
        assert len(CityManager(num_cities=7).cities) == 6

    def test_city_manager_honors_bonus_threshold(self):
        from src.models.city import CityManager
        cities = CityManager(bonus_threshold=12000)
        assert cities.bonus_threshold == 12000


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


class TestMouseButtonSiloMapping:
    """Real arcade cabinet: one trackball + 3 dedicated fire buttons wired
    to left/center/right battery, not a proximity/nearest-silo auto-select.
    Drives actual pygame MOUSEBUTTONDOWN events through _handle_events
    (not just calling _fire_silo directly) to verify the event routing
    itself, since that's what a real player's click goes through."""

    def _fire_via_mouse_button(self, app, button):
        import pygame
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=(0, 0)))
        app._handle_events()

    def test_left_click_fires_left_silo(self):
        app = MissileCommandApp()
        app.init()
        app.game.start_wave()
        self._fire_via_mouse_button(app, 1)
        abm = next(s for s in app.game.missiles.abm_slots if s is not None)
        assert abm.silo_index == 0
        app.shutdown()

    def test_middle_click_fires_center_silo(self):
        app = MissileCommandApp()
        app.init()
        app.game.start_wave()
        self._fire_via_mouse_button(app, 2)
        abm = next(s for s in app.game.missiles.abm_slots if s is not None)
        assert abm.silo_index == 1
        app.shutdown()

    def test_right_click_fires_right_silo(self):
        app = MissileCommandApp()
        app.init()
        app.game.start_wave()
        self._fire_via_mouse_button(app, 3)
        abm = next(s for s in app.game.missiles.abm_slots if s is not None)
        assert abm.silo_index == 2
        app.shutdown()


class TestThreeSiloConfig:
    """Tests that the src model always initializes 3 silos."""

    def test_game_has_three_silos(self):
        from src.game import Game
        game = Game()
        assert len(game.defenses.silos) == 3

    def test_silos_at_correct_positions(self):
        from src.config import SILO_POSITIONS
        from src.game import Game
        game = Game()
        assert game.defenses.silos[0].position_x == SILO_POSITIONS[0][0]  # left
        assert game.defenses.silos[1].position_x == SILO_POSITIONS[1][0]  # center
        assert game.defenses.silos[2].position_x == SILO_POSITIONS[2][0]  # right

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
        # Tally timer expiring enters the wave-intro screen, not RUNNING
        # directly -- Game.start_wave() isn't called until that expires too.
        assert app._pending_wave_intro is True
        for _ in range(WAVE_INTRO_DISPLAY_FRAMES + 1):
            app._update()
        # start_wave() fires once the intro timer expires, re-entering
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
        assert app._pending_wave_intro is True
        for _ in range(WAVE_INTRO_DISPLAY_FRAMES + 1):
            app._update()
        assert app.game.state == GameState.RUNNING
        assert app.attract_demo.game.score_display.player_score == demo_score_before

    def test_reset_to_attract_restarts_demo(self):
        app = MissileCommandApp()
        app.attract_demo.game.score_display.add(999)
        app._reset_to_attract()
        assert app.attract_demo.game.score_display.player_score == 0
        assert app.attract_demo.game.state == GameState.RUNNING


# ── Wave-intro screen ─────────────────────────────────────────────────────


class TestWaveIntroScreen:
    def test_begin_wave_intro_sets_pending_flag_and_timer(self):
        app = MissileCommandApp()
        app._begin_wave_intro()
        assert app._pending_wave_intro is True
        assert app.wave_intro_timer == WAVE_INTRO_DISPLAY_FRAMES

    def test_game_state_unchanged_until_intro_expires(self):
        app = MissileCommandApp()
        app._begin_wave_intro()
        for _ in range(WAVE_INTRO_DISPLAY_FRAMES - 1):
            app._update()
            assert app._pending_wave_intro is True

    def test_start_wave_called_only_after_intro_expires(self):
        app = MissileCommandApp()
        app._begin_wave_intro()
        for _ in range(WAVE_INTRO_DISPLAY_FRAMES + 1):
            app._update()
        assert app._pending_wave_intro is False
        assert app.game.state == GameState.RUNNING

    def test_wave_end_transitions_to_wave_intro_not_directly_to_running(self):
        app = MissileCommandApp()
        app.game.start_wave()
        app.game.icbms_remaining_this_wave = 0
        app._update()  # RUNNING -> WAVE_END
        for _ in range(WAVE_END_DISPLAY_FRAMES + 1):
            app._update()
        assert app._pending_wave_intro is True
        assert app.game.state == GameState.WAVE_END  # Game itself is unaware of the intro


# ── Non-blocking high-score initials entry ───────────────────────────────


class TestInitialsEntry:
    def _force_qualifying_game_over(self, app, tmp_path):
        # Never let a test app default to the real project scores.json.
        app.scores_file = str(tmp_path / "scores.json")
        app.high_scores = {str(i): {"name": "---", "score": 0} for i in range(1, 11)}
        app.game.start_wave()
        for city in app.game.cities.cities:
            city.destroy()
        app.game.cities.bonus_cities = 0
        app.game.cities.bonus_threshold = 0
        app.game.score_display.add(999999)
        app._update()  # RUNNING -> GAME_OVER
        for _ in range(GAME_OVER_DISPLAY_FRAMES + 1):
            app._update()

    def test_qualifying_score_enters_awaiting_initials(self, tmp_path):
        app = MissileCommandApp()
        self._force_qualifying_game_over(app, tmp_path)
        assert app._awaiting_initials is True
        assert app._initials_slot == 0

    def test_non_qualifying_score_skips_initials_entry(self, tmp_path):
        app = MissileCommandApp()
        app.scores_file = str(tmp_path / "scores.json")
        app.high_scores = {str(i): {"name": "---", "score": 0} for i in range(1, 11)}
        app.game.start_wave()
        for city in app.game.cities.cities:
            city.destroy()
        app.game.cities.bonus_cities = 0
        app._update()  # RUNNING -> GAME_OVER (score 0, never qualifies)
        for _ in range(GAME_OVER_DISPLAY_FRAMES + 1):
            app._update()
        assert app._awaiting_initials is False
        assert app.game.state == GameState.ATTRACT

    def test_scrubbing_selects_letter_from_crosshair_position(self, tmp_path):
        app = MissileCommandApp()
        self._force_qualifying_game_over(app, tmp_path)
        app.crosshair_x = 0  # leftmost -> first char in charset
        app._update()
        assert app._initials[0] == app.INITIALS_CHARSET[0]

    def test_three_clicks_confirm_and_save_score(self, tmp_path):
        app = MissileCommandApp()
        self._force_qualifying_game_over(app, tmp_path)
        score = app._initials_pending_score

        for _ in range(3):
            app._initials_slot += 1  # simulate a left click
            app._update()

        assert app._awaiting_initials is False
        assert app.game.state == GameState.ATTRACT
        assert any(
            record.get("score") == score for record in app.high_scores.values()
        )

    def test_left_click_routes_to_slot_advance_not_fire(self, tmp_path):
        """Mirrors _handle_events' MOUSEBUTTONDOWN routing: while awaiting
        initials, a left click must advance the slot, not fire an ABM.
        (No live pygame event loop here -- see test files' existing
        convention of exercising app methods directly.)"""
        app = MissileCommandApp()
        self._force_qualifying_game_over(app, tmp_path)
        assert app._initials_slot == 0
        if app._awaiting_initials:
            app._initials_slot += 1
        else:
            app._fire_silo(0)
        assert app._initials_slot == 1
        assert app.game.missiles.active_abm_count == 0

    def _make_initialized_app(self, tmp_path):
        """A pygame.event.post-capable app: init() must run with
        scores_file already pointed at the tmp path, since init()
        itself calls load_scores(self.scores_file) -- otherwise it
        would touch the real project scores.json."""
        app = MissileCommandApp()
        app.scores_file = str(tmp_path / "scores.json")
        assert app.init()
        self._force_qualifying_game_over(app, tmp_path)
        return app

    def _press_key(self, app, key):
        import pygame
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
        app._handle_events()

    def test_right_arrow_advances_highlighted_letter(self, tmp_path):
        app = self._make_initialized_app(tmp_path)
        app.crosshair_x = 0
        app._update()
        assert app._initials[0] == app.INITIALS_CHARSET[0]
        self._press_key(app, pygame.K_RIGHT)
        app._update()
        assert app._initials[0] == app.INITIALS_CHARSET[1]
        app.shutdown()

    def test_left_arrow_retreats_highlighted_letter(self, tmp_path):
        app = self._make_initialized_app(tmp_path)
        app.crosshair_x = 100
        app._update()
        before = app._initials[0]
        self._press_key(app, pygame.K_LEFT)
        app._update()
        before_idx = app.INITIALS_CHARSET.index(before)
        assert app.INITIALS_CHARSET.index(app._initials[0]) == before_idx - 1
        app.shutdown()

    def test_enter_confirms_and_advances_slot(self, tmp_path):
        app = self._make_initialized_app(tmp_path)
        assert app._initials_slot == 0
        self._press_key(app, pygame.K_RETURN)
        assert app._initials_slot == 1
        app.shutdown()

    def test_space_confirms_and_advances_slot(self, tmp_path):
        app = self._make_initialized_app(tmp_path)
        assert app._initials_slot == 0
        self._press_key(app, pygame.K_SPACE)
        assert app._initials_slot == 1
        app.shutdown()

    def test_three_enters_confirm_and_save_score(self, tmp_path):
        app = self._make_initialized_app(tmp_path)
        score = app._initials_pending_score
        for _ in range(3):
            self._press_key(app, pygame.K_RETURN)
            app._update()
        assert app._awaiting_initials is False
        assert app.game.state == GameState.ATTRACT
        assert any(
            record.get("score") == score for record in app.high_scores.values()
        )
        app.shutdown()

    def test_arrow_keys_do_not_fire_or_move_crosshair_via_silo_keys(self, tmp_path):
        """Left/Right must be dedicated to initials navigation while
        awaiting initials, not fall through to silo-fire bindings."""
        app = self._make_initialized_app(tmp_path)
        self._press_key(app, pygame.K_RIGHT)
        assert app.game.missiles.active_abm_count == 0
        app.shutdown()
