"""
Attract-mode demo AI for Missile Command.

Per the disassembly: attract-mode gameplay isn't pre-recorded -- the
computer actually plays through a wave. It targets ICBMs in the order
they appear, aiming the crosshair at the point a missile will reach
in 16 frames, then fires from the closest launcher. It never keeps
more than two ABMs in flight at once, which is why the computer
player looks a bit relaxed by the end of the wave.

References:
    - Missile Command Disassembly.pdf (Odds & Ends)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config import SCREEN_HEIGHT, SCREEN_WIDTH
from src.game import Game, GameState
from src.models.missile import from_fixed

TARGET_LEAD_FRAMES = 16
MAX_CONCURRENT_ABMS = 2


@dataclass
class AttractDemo:
    """Owns a hidden :class:`Game` and plays it automatically."""

    game: Game = field(default_factory=Game)
    crosshair_pos: tuple[int, int] = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
    _engaged_ids: set = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        self.game.start_wave()

    def restart(self) -> None:
        """Start a fresh demo game (e.g. after the demo wave ends)."""
        self.game = Game()
        self.game.start_wave()
        self._engaged_ids.clear()

    def update(self) -> None:
        """Advance the demo by one frame."""
        if self.game.state != GameState.RUNNING:
            self.restart()
            return
        self._autoplay_fire()
        self.game.update()

    def _autoplay_fire(self) -> None:
        if self.game.missiles.active_abm_count >= MAX_CONCURRENT_ABMS:
            return

        active_ids = set()
        target = None
        for missile in self.game.missiles.icbm_slots:
            if missile is not None and missile.is_active:
                active_ids.add(id(missile))
                if target is None and id(missile) not in self._engaged_ids:
                    target = missile
        self._engaged_ids &= active_ids  # drop ids of missiles no longer in flight

        if target is None:
            return

        target_x, target_y = self._predict_position(target, TARGET_LEAD_FRAMES)
        self.crosshair_pos = (target_x, target_y)
        if self.game.fire_nearest(target_x, target_y):
            self._engaged_ids.add(id(target))

    def _predict_position(self, missile, frames: int) -> tuple[int, int]:
        """Predict where *missile* will be in *frames* frames."""
        x_fp = missile.current_x_fp + missile.x_increment * frames
        y_fp = missile.current_y_fp + missile.y_increment * frames
        return from_fixed(x_fp), from_fixed(y_fp)
