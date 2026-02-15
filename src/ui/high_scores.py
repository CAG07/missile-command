"""
High-score persistence for Missile Command.

Loads and saves a top-10 leaderboard in JSON format, matching the
structure already used by the legacy ``scores.json`` file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


_DEFAULT_SCORES_FILE = "scores.json"

_DEFAULT_ENTRIES: list[dict[str, object]] = [
    {"name": "---", "score": 0} for _ in range(10)
]


@dataclass
class HighScoreManager:
    """Manages a persistent top-10 leaderboard.

    Entries are kept in descending score order (index 0 = #1).
    """

    filepath: str = _DEFAULT_SCORES_FILE
    entries: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.entries:
            self.load()

    # ── I/O ─────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load high scores from *filepath*.

        Falls back to defaults if the file is missing or malformed.
        """
        if os.path.isfile(self.filepath):
            try:
                with open(self.filepath, "r") as fh:
                    data = json.load(fh)
                self.entries = self._parse(data)
                return
            except Exception:
                pass
        self.entries = [dict(e) for e in _DEFAULT_ENTRIES]

    @staticmethod
    def _parse(data: object) -> list[dict[str, object]]:
        """Normalise the legacy ``{"1": {...}, "2": {...}}`` format."""
        entries: list[dict[str, object]] = []
        if isinstance(data, dict):
            for key in sorted(data.keys(), key=lambda k: int(k)):
                record = data[key]
                entries.append({
                    "name": str(record.get("name", "---")),
                    "score": int(str(record.get("score", 0)).strip()),
                })
        elif isinstance(data, list):
            for record in data:
                entries.append({
                    "name": str(record.get("name", "---")),
                    "score": int(str(record.get("score", 0)).strip()),
                })
        # Pad / trim to exactly 10
        while len(entries) < 10:
            entries.append({"name": "---", "score": 0})
        return entries[:10]

    def save(self) -> None:
        """Persist the current leaderboard to *filepath*."""
        data: dict[str, dict[str, object]] = {}
        for i, entry in enumerate(self.entries):
            data[str(i + 1)] = {"name": entry["name"], "score": entry["score"]}
        try:
            with open(self.filepath, "w") as fh:
                json.dump(data, fh)
        except OSError:
            pass

    # ── Queries ─────────────────────────────────────────────────────────

    @property
    def top_score(self) -> int:
        """Return the highest score on the leaderboard."""
        if not self.entries:
            return 0
        return int(self.entries[0].get("score", 0))

    def qualifies(self, score: int) -> bool:
        """Return True if *score* would make it into the top 10."""
        if len(self.entries) < 10:
            return True
        return score > int(self.entries[-1].get("score", 0))

    # ── Mutations ───────────────────────────────────────────────────────

    def insert(self, name: str, score: int) -> int:
        """Insert a new entry and return its 1-based position.

        Returns 0 if the score did not qualify.
        """
        if not self.qualifies(score):
            return 0

        new_entry = {"name": name, "score": score}
        # Find insertion point (descending order)
        pos = 0
        for i, entry in enumerate(self.entries):
            if score > int(entry.get("score", 0)):
                pos = i
                break
        else:
            pos = len(self.entries)

        self.entries.insert(pos, new_entry)
        self.entries = self.entries[:10]
        self.save()
        return pos + 1  # 1-based
