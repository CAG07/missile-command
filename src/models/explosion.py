"""
Explosion model for Missile Command.

Implements octagonal (not circular) explosions with the original arcade's
3/8 slope, group-based update scheduling (5 groups of 4), and ICBM-only
collision detection performed every 5 frames.

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from src.config import (
    EXPLOSION_COLLISION_ALTITUDE_MIN,
    EXPLOSION_GROUPS,
    EXPLOSION_MAX_RADIUS,
    EXPLOSION_OCTAGON_SLOPE_DEN,
    EXPLOSION_OCTAGON_SLOPE_NUM,
    EXPLOSIONS_PER_GROUP,
    MAX_EXPLOSION_SLOTS,
)


# ── Explosion lifecycle ────────────────────────────────────────────────────


class ExplosionState(Enum):
    EXPANDING = auto()
    HOLDING = auto()
    CONTRACTING = auto()
    DONE = auto()


# ── Octagon geometry ───────────────────────────────────────────────────────


def octagon_points(
    cx: int, cy: int, radius: int,
    slope_num: int = EXPLOSION_OCTAGON_SLOPE_NUM,
    slope_den: int = EXPLOSION_OCTAGON_SLOPE_DEN,
) -> list[tuple[int, int]]:
    """Return the 8 vertices of an octagon centred at (*cx*, *cy*).

    The octagon uses a 3/8 slope (more square-looking than a 1/2 slope)
    matching the original Atari hardware.

    Vertex order: top, top-right, right, bottom-right, bottom,
    bottom-left, left, top-left.
    """
    # Cutoff length along each axis where the chamfer begins
    cut = (radius * slope_num) // slope_den
    return [
        (cx, cy - radius),              # top
        (cx + radius - cut, cy - cut),  # top-right
        (cx + radius, cy),              # right
        (cx + radius - cut, cy + cut),  # bottom-right
        (cx, cy + radius),              # bottom
        (cx - radius + cut, cy + cut),  # bottom-left
        (cx - radius, cy),              # left
        (cx - radius + cut, cy - cut),  # top-left
    ]


def point_in_octagon(
    px: int, py: int,
    cx: int, cy: int,
    radius: int,
    slope_num: int = EXPLOSION_OCTAGON_SLOPE_NUM,
    slope_den: int = EXPLOSION_OCTAGON_SLOPE_DEN,
) -> bool:
    """Return True if point (*px*, *py*) is inside the octagon.

    The octagon is axis-aligned and centred at (*cx*, *cy*).
    Uses the 3/8 slope from the original hardware.
    """
    dx = abs(px - cx)
    dy = abs(py - cy)
    if dx > radius or dy > radius:
        return False
    # The chamfer line for a 3/8-slope octagon:
    #   dx + (slope_den/slope_num) * dy <= radius  (first-quadrant test)
    #   but we use the equivalent integer form to avoid floats:
    #   slope_num * dx + slope_den * dy <= slope_den * radius
    # Actually for a cut corner, the constraint is:
    #   dx * slope_den + dy * slope_den <= radius * slope_den + cut * slope_den
    # Simplify: use the standard octagon inequality
    #   max(dx, dy, (dx+dy) * slope_den/(slope_den+slope_num)) <= radius
    # More precisely for 3/8 slope: the corner is clipped where
    #   dx + dy > radius + cut, with cut = radius * 3/8
    cut = (radius * slope_num) // slope_den
    if dx + dy > radius + cut:
        return False
    return True


# ── Explosion ──────────────────────────────────────────────────────────────


@dataclass
class Explosion:
    """A single octagonal explosion.

    Lifecycle: expands over several frames, holds at maximum radius,
    then contracts.  Part of a group-based slot system where only one
    group (4 explosions) is updated per frame.

    Collision detection against ICBMs is performed when the explosion is
    drawn (every 5 frames for its group).  ABMs can pass through
    unharmed.  No collision testing below altitude (Y) 33.
    """

    center_x: int
    center_y: int
    max_radius: int = EXPLOSION_MAX_RADIUS
    expand_rate: int = 1          # radius units per update
    hold_frames: int = 10         # frames to hold at max radius
    contract_rate: int = 1        # radius units per update while shrinking
    group_id: int = 0             # 0-4, determines update scheduling

    # Runtime state
    current_radius: int = 0
    state: ExplosionState = ExplosionState.EXPANDING
    frame_counter: int = 0
    is_active: bool = True

    @property
    def center_pos(self) -> tuple[int, int]:
        return (self.center_x, self.center_y)

    def update(self) -> None:
        """Advance one explosion tick (called when group is scheduled)."""
        if not self.is_active:
            return

        if self.state == ExplosionState.EXPANDING:
            self.current_radius += self.expand_rate
            if self.current_radius >= self.max_radius:
                self.current_radius = self.max_radius
                self.state = ExplosionState.HOLDING
                self.frame_counter = 0

        elif self.state == ExplosionState.HOLDING:
            self.frame_counter += 1
            if self.frame_counter >= self.hold_frames:
                self.state = ExplosionState.CONTRACTING

        elif self.state == ExplosionState.CONTRACTING:
            self.current_radius -= self.contract_rate
            if self.current_radius <= 0:
                self.current_radius = 0
                self.state = ExplosionState.DONE
                self.is_active = False

    def get_octagon_points(self) -> list[tuple[int, int]]:
        """Return the 8 vertices of the current octagon."""
        return octagon_points(self.center_x, self.center_y, self.current_radius)

    def collides_with(self, x: int, y: int) -> bool:
        """Return True if point (*x*, *y*) is inside the explosion.

        No collision below altitude EXPLOSION_COLLISION_ALTITUDE_MIN
        (line 33).  Only used for ICBM collision testing.
        """
        if not self.is_active or self.current_radius <= 0:
            return False
        if y < EXPLOSION_COLLISION_ALTITUDE_MIN:
            return False
        return point_in_octagon(
            x, y,
            self.center_x, self.center_y,
            self.current_radius,
        )


# ── Explosion Manager (group scheduler) ───────────────────────────────────


@dataclass
class ExplosionManager:
    """Manages 20 explosion slots divided into 5 groups of 4.

    Only one group is updated per frame, cycling through groups 0-4.
    Collision detection for a group occurs when that group is updated.
    """

    slots: list[Optional[Explosion]] = field(
        default_factory=lambda: [None] * MAX_EXPLOSION_SLOTS,
    )
    current_group: int = 0  # 0-4, which group updates this frame

    # Group helpers ───────────────────────────────────────────────────────

    def _group_indices(self, group_id: int) -> range:
        """Return slot indices for *group_id*."""
        start = group_id * EXPLOSIONS_PER_GROUP
        return range(start, start + EXPLOSIONS_PER_GROUP)

    # Adding explosions ───────────────────────────────────────────────────

    def add(self, explosion: Explosion) -> bool:
        """Place *explosion* into a free slot.  Returns False if full."""
        for i in range(MAX_EXPLOSION_SLOTS):
            if self.slots[i] is None or not self.slots[i].is_active:
                explosion.group_id = i // EXPLOSIONS_PER_GROUP
                self.slots[i] = explosion
                return True
        return False

    # Per-frame update ────────────────────────────────────────────────────

    def update(self) -> list[Explosion]:
        """Update the current group and advance the group counter.

        Returns the list of active explosions in the updated group
        (for collision testing by the caller).
        """
        updated: list[Explosion] = []
        for i in self._group_indices(self.current_group):
            exp = self.slots[i]
            if exp is not None and exp.is_active:
                exp.update()
                updated.append(exp)
            # Clean up finished explosions
            if exp is not None and not exp.is_active:
                self.slots[i] = None
        self.current_group = (self.current_group + 1) % EXPLOSION_GROUPS
        return updated

    # Collision helpers ───────────────────────────────────────────────────

    def check_icbm_collisions(
        self,
        explosions: list[Explosion],
        icbm_positions: list[tuple[int, int, int]],
    ) -> list[int]:
        """Return indices of ICBMs hit by any explosion in *explosions*.

        *icbm_positions* is a list of (x, y, slot_index) tuples.
        Collision is only tested when a group is drawn (every 5 frames).
        """
        hit: list[int] = []
        for ex in explosions:
            for x, y, idx in icbm_positions:
                if ex.collides_with(x, y):
                    hit.append(idx)
        return hit

    # Queries ─────────────────────────────────────────────────────────────

    @property
    def active_explosion_centers(self) -> list[tuple[int, int]]:
        """Return centre positions of all active explosions."""
        return [
            e.center_pos
            for e in self.slots
            if e is not None and e.is_active
        ]

    @property
    def active_count(self) -> int:
        return sum(1 for e in self.slots if e is not None and e.is_active)

    def reset(self) -> None:
        """Clear all slots (wave reset)."""
        self.slots = [None] * MAX_EXPLOSION_SLOTS
        self.current_group = 0
