"""
UI text utilities for Missile Command.

Provides score rendering and HUD text helpers for the arcade-style
interface.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoreDisplay:
    """Tracks and formats the player score and high-score for HUD display."""

    player_score: int = 0
    high_score: int = 0

    def add(self, points: int) -> None:
        """Add *points* to the player score and update high score."""
        self.player_score += points
        if self.player_score > self.high_score:
            self.high_score = self.player_score

    def reset(self) -> None:
        """Reset player score (high score persists)."""
        self.player_score = 0

    def format_score(self) -> str:
        return f"SCORE: {self.player_score}"

    def format_high_score(self) -> str:
        return f"HIGH: {self.high_score}"
