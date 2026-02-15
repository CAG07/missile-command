"""
High-score persistence for Missile Command.

Loads and saves a top-10 leaderboard in JSON format, matching the
structure used by the existing ``scores.json`` file.

The dict layout is ``{"1": {"name": ..., "score": ...}, ...}`` with
string keys ``"1"`` through ``"10"`` in descending rank order.

These functions mirror the legacy helpers in ``functions.py``
(``load_scores``, ``save_high_scores``, ``update_high_scores``,
``check_high_score``) but are importable from the ``src`` package
without pulling in pygame or the old config module.
"""

from __future__ import annotations

import json
import os

_DEFAULT_SCORES_FILE = "scores.json"


# ── I/O helpers ─────────────────────────────────────────────────────────────


def load_scores(filepath: str = _DEFAULT_SCORES_FILE) -> dict:
    """Open a JSON file containing scores and return a dict.

    Falls back to an empty top-10 table if the file is missing or
    malformed.
    """
    if os.path.isfile(filepath):
        try:
            with open(filepath) as f:
                data = json.load(f)
            # Normalise any stringified scores (e.g. "  500")
            for record in data.values():
                record["score"] = int(str(record.get("score", 0)).strip())
            return data
        except Exception:
            pass
    return _default_scores()


def save_high_scores(filepath: str, high_scores: dict) -> None:
    """Save high-scores dict to *filepath*."""
    j = json.dumps(high_scores)
    try:
        with open(filepath, "w") as f:
            f.write(j)
    except OSError:
        pass


# ── Score checking / updating ───────────────────────────────────────────────


def check_high_score(score: int, high_scores: dict) -> int:
    """Return the 1-based position a *score* would occupy, or 0."""
    score_pos = 0
    for pos, record in high_scores.items():
        if score > int(str(record["score"]).strip()) and score_pos == 0:
            score_pos = int(pos)
    return score_pos


def update_high_scores(
    score: int, name: str, high_scores: dict
) -> dict:
    """Insert *score* / *name* into *high_scores* if it qualifies.

    Re-orders the dict so that lower entries shift down.  Returns the
    (possibly modified) dict.
    """
    score_pos = check_high_score(score, high_scores)

    if score_pos > 0:
        max_pos = 10
        for pos in range(max_pos, score_pos, -1):
            if pos <= max_pos and pos > 1:
                high_scores[str(pos)]["name"] = high_scores[str(pos - 1)]["name"]
                high_scores[str(pos)]["score"] = high_scores[str(pos - 1)]["score"]
        high_scores[str(score_pos)]["name"] = name
        high_scores[str(score_pos)]["score"] = int(score)

    return high_scores


# ── Convenience queries ─────────────────────────────────────────────────────


def get_top_score(high_scores: dict) -> int:
    """Return the highest score from the leaderboard dict."""
    if not high_scores:
        return 0
    return int(str(high_scores.get("1", {}).get("score", 0)).strip())


# ── Internal helpers ────────────────────────────────────────────────────────


def _default_scores() -> dict:
    """Return a fresh default top-10 dict."""
    return {
        str(i): {"name": "---", "score": 0} for i in range(1, 11)
    }
