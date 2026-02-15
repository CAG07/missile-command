"""User interface components."""

from .audio import AudioManager, SoundEvent
from .high_scores import HighScoreManager
from .text import ScoreDisplay

__all__ = ["AudioManager", "HighScoreManager", "ScoreDisplay", "SoundEvent"]