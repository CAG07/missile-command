"""
Input handler for Missile Command.

Maps player input events to game actions (silo selection, firing, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class GameAction(Enum):
    """Actions the player can trigger."""
    FIRE_LEFT = auto()
    FIRE_CENTER = auto()
    FIRE_RIGHT = auto()
    FIRE_NEAREST = auto()
    PAUSE = auto()
    QUIT = auto()
    NONE = auto()


@dataclass
class InputEvent:
    """Abstract input event consumed by the game loop."""
    action: GameAction
    target_x: int = 0
    target_y: int = 0
