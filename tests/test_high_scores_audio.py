"""
Tests for high score persistence and audio manager.

Covers loading, saving, checking, and updating high scores via the
function-based API that mirrors the legacy ``functions.py`` helpers,
as well as the AudioManager's graceful fallback behaviour.
"""

import json
import os
import tempfile

import pytest

from src.ui.audio import AudioManager, SoundEvent
from src.ui.high_scores import (
    check_high_score,
    get_top_score,
    load_scores,
    save_high_scores,
    update_high_scores,
)


# ── High Score Persistence ──────────────────────────────────────────────────


class TestLoadScores:
    def test_load_existing_file(self, tmp_path):
        filepath = str(tmp_path / "scores.json")
        data = {
            str(i): {"name": f"P{i}", "score": (11 - i) * 100}
            for i in range(1, 11)
        }
        with open(filepath, "w") as f:
            json.dump(data, f)
        result = load_scores(filepath)
        assert result["1"]["name"] == "P1"
        assert result["1"]["score"] == 1000

    def test_load_missing_file_returns_defaults(self, tmp_path):
        filepath = str(tmp_path / "nonexistent.json")
        result = load_scores(filepath)
        assert len(result) == 10
        assert result["1"]["score"] == 0
        assert result["1"]["name"] == "---"

    def test_load_normalises_string_scores(self, tmp_path):
        filepath = str(tmp_path / "scores.json")
        data = {"1": {"name": "A", "score": "  500"}}
        # pad remaining entries
        for i in range(2, 11):
            data[str(i)] = {"name": "---", "score": 0}
        with open(filepath, "w") as f:
            json.dump(data, f)
        result = load_scores(filepath)
        assert result["1"]["score"] == 500

    def test_load_malformed_returns_defaults(self, tmp_path):
        filepath = str(tmp_path / "scores.json")
        with open(filepath, "w") as f:
            f.write("NOT JSON")
        result = load_scores(filepath)
        assert len(result) == 10
        assert result["1"]["score"] == 0


class TestSaveHighScores:
    def test_save_and_reload(self, tmp_path):
        filepath = str(tmp_path / "scores.json")
        data = {
            str(i): {"name": f"P{i}", "score": (11 - i) * 100}
            for i in range(1, 11)
        }
        save_high_scores(filepath, data)
        assert os.path.isfile(filepath)
        reloaded = load_scores(filepath)
        assert reloaded["1"]["name"] == "P1"
        assert reloaded["1"]["score"] == 1000


class TestCheckHighScore:
    def _make_scores(self):
        return {
            str(i): {"name": f"P{i}", "score": (11 - i) * 100}
            for i in range(1, 11)
        }

    def test_qualifies_first(self):
        scores = self._make_scores()
        pos = check_high_score(9999, scores)
        assert pos == 1

    def test_qualifies_middle(self):
        scores = self._make_scores()
        # Scores: 1000, 900, 800, 700, 600, 500, 400, 300, 200, 100
        pos = check_high_score(550, scores)
        assert pos == 6

    def test_does_not_qualify(self):
        scores = self._make_scores()
        pos = check_high_score(50, scores)
        assert pos == 0

    def test_equal_score_does_not_qualify(self):
        scores = self._make_scores()
        pos = check_high_score(100, scores)
        assert pos == 0


class TestUpdateHighScores:
    def _make_scores(self):
        return {
            str(i): {"name": f"P{i}", "score": (11 - i) * 100}
            for i in range(1, 11)
        }

    def test_insert_top_score(self):
        scores = self._make_scores()
        updated = update_high_scores(9999, "NEW", scores)
        assert updated["1"]["name"] == "NEW"
        assert updated["1"]["score"] == 9999
        # Previous #1 should shift to #2
        assert updated["2"]["name"] == "P1"

    def test_insert_middle(self):
        scores = self._make_scores()
        updated = update_high_scores(550, "MID", scores)
        assert updated["6"]["name"] == "MID"
        assert updated["6"]["score"] == 550
        # Previous #6 shifts to #7
        assert updated["7"]["name"] == "P6"

    def test_no_insert_for_low_score(self):
        scores = self._make_scores()
        updated = update_high_scores(50, "LOW", scores)
        # Nothing should change
        assert updated["10"]["name"] == "P10"


class TestGetTopScore:
    def test_top_score(self):
        scores = {
            str(i): {"name": f"P{i}", "score": (11 - i) * 100}
            for i in range(1, 11)
        }
        assert get_top_score(scores) == 1000

    def test_empty_dict(self):
        assert get_top_score({}) == 0

    def test_string_score(self):
        scores = {"1": {"name": "A", "score": "  500"}}
        assert get_top_score(scores) == 500


# ── Audio Manager ───────────────────────────────────────────────────────────


class TestAudioManager:
    def test_disabled_audio_does_not_init(self):
        am = AudioManager(enabled=False)
        result = am.init()
        assert result is False
        assert am._initialized is False

    def test_play_when_not_initialized(self):
        am = AudioManager(enabled=False)
        # Should not raise
        am.play(SoundEvent.EXPLOSION)

    def test_shutdown_when_not_initialized(self):
        am = AudioManager(enabled=False)
        # Should not raise
        am.shutdown()

    def test_sound_event_enum(self):
        assert SoundEvent.FIRE_ABM is not None
        assert SoundEvent.EXPLOSION is not None
        assert SoundEvent.GAME_OVER is not None
        assert SoundEvent.WAVE_END is not None
        assert SoundEvent.BONUS_CITY is not None

    def test_missing_sfx_dir(self):
        am = AudioManager(sfx_dir="/nonexistent/path")
        # _load_sounds should not raise even with bad dir
        am._load_sounds()
        assert len(am._sounds) == 0


# ── Game Over Integration ──────────────────────────────────────────────────


class TestGameOverHighScoreIntegration:
    def test_game_over_triggers_high_score_save(self, tmp_path):
        """When the game transitions to GAME_OVER the score should be
        persisted to the high-score file."""
        from src.game import Game, GameState

        filepath = str(tmp_path / "scores.json")
        high_scores = load_scores(filepath)
        game = Game()
        game.start_wave()
        game.score_display.add(5000)

        # Force game over
        for city in game.cities.cities:
            city.destroy()
        game.cities.bonus_cities = 0
        state = game.update()
        assert state == GameState.GAME_OVER

        # Simulate what MissileCommandApp._update does
        high_scores = update_high_scores(
            game.score_display.player_score, "---", high_scores
        )
        save_high_scores(filepath, high_scores)

        # Verify persistence
        reloaded = load_scores(filepath)
        assert reloaded["1"]["score"] == 5000

    def test_high_score_loaded_into_score_display(self, tmp_path):
        """ScoreDisplay.high_score should be initialised from the
        persisted leaderboard."""
        from src.game import Game

        filepath = str(tmp_path / "scores.json")
        data = {str(i): {"name": "---", "score": 0} for i in range(1, 11)}
        data["1"]["score"] = 75400
        data["1"]["name"] = "John"
        with open(filepath, "w") as f:
            json.dump(data, f)

        high_scores = load_scores(filepath)
        game = Game()
        game.score_display.high_score = get_top_score(high_scores)
        assert game.score_display.high_score == 75400
