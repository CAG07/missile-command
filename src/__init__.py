"""
Missile Command - Arcade-accurate recreation
Based on 1980 Atari arcade game disassembly (revision 3)
"""

__version__ = "1.0.0"

from .game import Game, GameState

__all__ = ["Game", "GameState"]