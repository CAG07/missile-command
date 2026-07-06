"""
Tests for src/attract.py -- the attract-mode autoplay demo AI.
"""

from src.attract import AttractDemo, MAX_CONCURRENT_ABMS, TARGET_LEAD_FRAMES
from src.game import GameState
from src.models.missile import ICBM


class TestAttractDemo:
    def test_starts_running(self):
        demo = AttractDemo()
        assert demo.game.state == GameState.RUNNING

    def test_restart_resets_game(self):
        demo = AttractDemo()
        demo.game.score_display.add(500)
        demo.restart()
        assert demo.game.score_display.player_score == 0
        assert demo.game.state == GameState.RUNNING

    def test_update_advances_frame_count(self):
        demo = AttractDemo()
        before = demo.game.frame_count
        demo.update()
        assert demo.game.frame_count == before + 1

    def test_restarts_automatically_after_game_over(self):
        demo = AttractDemo()
        for city in demo.game.cities.cities:
            city.destroy()
        demo.game.cities.bonus_cities = 0
        demo.game.update()
        assert demo.game.state == GameState.GAME_OVER
        demo.update()
        assert demo.game.state == GameState.RUNNING
        assert demo.game.score_display.player_score == 0

    def test_never_exceeds_max_concurrent_abms(self):
        demo = AttractDemo()
        for _ in range(300):
            demo.update()
            assert demo.game.missiles.active_abm_count <= MAX_CONCURRENT_ABMS

    def test_fires_at_incoming_icbms_over_time(self):
        demo = AttractDemo()
        fired = False
        for _ in range(600):
            demo.update()
            if demo.game.missiles.active_abm_count > 0:
                fired = True
                break
        assert fired

    def test_predict_position_uses_lead_frames(self):
        demo = AttractDemo()
        icbm = ICBM(entry_x=100, entry_y=0, target_x=100, target_y=220, speed=2)
        x, y = demo._predict_position(icbm, TARGET_LEAD_FRAMES)
        # Predicted position should have advanced further than current position
        assert y > icbm.current_y

    def test_crosshair_pos_updates_when_firing(self):
        demo = AttractDemo()
        start_pos = demo.crosshair_pos
        moved = False
        for _ in range(300):
            demo.update()
            if demo.crosshair_pos != start_pos:
                moved = True
                break
        assert moved

    def test_engaged_ids_drop_missiles_no_longer_active(self):
        demo = AttractDemo()
        for _ in range(300):
            demo.update()
        # After many frames, engaged ids should never grow unbounded --
        # bounded by active ICBM slot count.
        assert len(demo._engaged_ids) <= 8
