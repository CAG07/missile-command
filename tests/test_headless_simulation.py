"""
Headless simulation test (no display required).

Runs up to 20 waves with a scripted bot and asserts the game never
crashes and never exceeds any slot-table limit, per SPEC.md's
acceptance criteria: "Headless simulation test: run 20 waves with a
scripted bot without crash."

The scripted bot fires at each incoming missile's predicted position
(leading it, the same approach used by src/attract.py's autoplay AI)
rather than its assigned target -- aiming at the target itself means
the interception explosion often arrives at the same moment as (or
after) the missile's impact, since collision is only checked once
per 5 frames per the disassembly's explosion-group scheduling.

The bot is not required to survive all 20 waves -- the mercy rule
caps city losses at 3/wave, so a weak-but-functioning defense will
eventually lose via attrition (a legitimate GAME_OVER, not a crash).
What matters is that the simulation runs to completion (or to
GAME_OVER) without exceeding any slot limit or raising.
"""

from __future__ import annotations

import random

from src.config import (
    MAX_ABM_SLOTS,
    MAX_ICBM_SLOTS,
    MAX_EXPLOSION_SLOTS,
    MAX_SMART_BOMBS,
)
from src.game import Game, GameState
from src.models.missile import from_fixed

BOT_MAX_CONCURRENT_ABMS = 4
BOT_LEAD_FRAMES = 16
BOT_FIRE_INTERVAL_FRAMES = 2


def _predict_position(missile, frames: int) -> tuple[int, int]:
    """Predict where *missile* will be in *frames* frames (8.8 fixed-point)."""
    x_fp = missile.current_x_fp + missile.x_increment * frames
    y_fp = missile.current_y_fp + missile.y_increment * frames
    return from_fixed(x_fp), from_fixed(y_fp)


def _scripted_bot_frame(game: Game, frame: int) -> bool:
    """A simple scripted defender: lead-fire the nearest silo at the
    first active incoming missile. Returns True if a shot was fired."""
    if frame % BOT_FIRE_INTERVAL_FRAMES != 0:
        return False
    if game.missiles.active_abm_count >= BOT_MAX_CONCURRENT_ABMS:
        return False
    for missile in game.missiles.icbm_slots:
        if missile is not None and missile.is_active:
            tx, ty = _predict_position(missile, BOT_LEAD_FRAMES)
            return game.fire_nearest(tx, ty)
    return False


def _run_simulation(seed: int, max_wave: int = 20, max_frames: int = 200_000) -> Game:
    """Run the scripted-bot simulation and return the final Game state."""
    random.seed(seed)
    game = Game()
    game.start_wave()

    frame = 0
    while game.wave_number <= max_wave and frame < max_frames:
        _scripted_bot_frame(game, frame)
        state = game.update()

        # Slot tables must never exceed their hardware-mirrored limits.
        assert game.missiles.active_abm_count <= MAX_ABM_SLOTS
        assert game.missiles.active_icbm_count <= MAX_ICBM_SLOTS
        assert game.explosions.active_count <= MAX_EXPLOSION_SLOTS
        assert game.missiles.smart_bomb_count <= MAX_SMART_BOMBS

        if state == GameState.WAVE_END:
            game.start_wave()
        elif state == GameState.GAME_OVER:
            break

        frame += 1

    assert frame < max_frames, "simulation did not terminate in a reasonable frame budget"
    return game


class TestHeadlessSimulation:
    def test_runs_20_waves_without_crashing(self):
        game = _run_simulation(seed=1234)
        assert game.wave_number >= 1
        # A functioning defense should score at least some kills before
        # eventually succumbing to attrition (catches a fully-inert-
        # defense regression, e.g. fire_nearest silently broken).
        assert game.score_display.player_score > 0

    def test_runs_20_waves_across_many_seeds_without_crashing(self):
        for seed in range(10):
            game = _run_simulation(seed=seed, max_wave=20)
            assert game.wave_number >= 1
            assert game.score_display.player_score > 0

    def test_runs_with_no_defense_and_no_crash(self):
        """A pathological "never fires" bot should still not crash the
        simulation and should reach game over via attrition."""
        random.seed(4321)
        game = Game()
        game.start_wave()

        frame = 0
        max_frames = 100_000
        while frame < max_frames:
            state = game.update()
            assert game.missiles.active_abm_count <= MAX_ABM_SLOTS
            assert game.missiles.active_icbm_count <= MAX_ICBM_SLOTS
            assert game.explosions.active_count <= MAX_EXPLOSION_SLOTS

            if state == GameState.WAVE_END:
                if game.wave_number > 20:
                    break
                game.start_wave()
            elif state == GameState.GAME_OVER:
                break
            frame += 1

        assert frame < max_frames, "simulation did not terminate in a reasonable frame budget"
        assert game.state == GameState.GAME_OVER
        assert game.cities.active_count == 0
