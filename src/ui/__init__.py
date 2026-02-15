"""User interface components."""

from .audio import AudioManager, SoundEvent
from .high_scores import (
    check_high_score,
    get_top_score,
    load_scores,
    save_high_scores,
    update_high_scores,
)
from .text import ScoreDisplay

__all__ = [
    "AudioManager",
    "ScoreDisplay",
    "SoundEvent",
    "check_high_score",
    "get_top_score",
    "load_scores",
    "save_high_scores",
    "update_high_scores",
]