"""
Missile Command - Arcade-accurate recreation
Based on 1980 Atari arcade game disassembly (revision 3)
"""

__version__ = "1.0.0"

from .game import Game, GameState
from .config import *  # noqa: F401,F403

__all__ = ["Game", "GameState"]