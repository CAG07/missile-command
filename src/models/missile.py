"""
Missile types for Missile Command.

Implements ABM, ICBM, SmartBomb and Flier using the original arcade's
fixed-point 8.8 movement system and slot-based architecture.

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from src.config import (
    ABM_SPEED_CENTER,
    ABM_SPEED_SIDE,
    FIXED_POINT_SCALE,
    FIXED_POINT_SHIFT,
    MAX_ABM_SLOTS,
    MAX_ICBM_SLOTS,
    MAX_SMART_BOMBS,
    MIRV_ALTITUDE_HIGH,
    MIRV_ALTITUDE_LOW,
    MIRV_MAX_CHILDREN,
    WAVE_SPEEDS,
)


# ── Fixed-point 8.8 math utilities ─────────────────────────────────────────


def to_fixed(value: int) -> int:
    """Convert an integer to 8.8 fixed-point representation."""
    return value << FIXED_POINT_SHIFT


def from_fixed(value: int) -> int:
    """Convert an 8.8 fixed-point value back to an integer (truncates)."""
    return value >> FIXED_POINT_SHIFT


def fixed_mul(a: int, b: int) -> int:
    """Multiply two 8.8 fixed-point values."""
    return (a * b) >> FIXED_POINT_SHIFT


def distance_approx(x1: int, y1: int, x2: int, y2: int) -> int:
    """Approximate distance capped at 255.

    Uses the fast octagonal approximation common on 6502 hardware:
        dist ≈ max(|dx|, |dy|) + (3/8) * min(|dx|, |dy|)

    All values are in integer (screen) coordinates.
    """
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    if dx < dy:
        dx, dy = dy, dx
    dist = dx + ((3 * dy) >> 3)
    return min(dist, 255)


def compute_increments(
    sx: int, sy: int, tx: int, ty: int, speed: int
) -> tuple[int, int]:
    """Return (x_increment, y_increment) in 8.8 fixed-point.

    Divides the X and Y components by the distance to the target, then
    scales by *speed*.  This mirrors the original ROM's increment
    calculation.  See $5379 in the disassembly.
    """
    dist = distance_approx(sx, sy, tx, ty)
    if dist == 0:
        return (0, 0)
    dx = tx - sx
    dy = ty - sy
    x_inc = (dx * speed * FIXED_POINT_SCALE) // dist
    y_inc = (dy * speed * FIXED_POINT_SCALE) // dist
    return (x_inc, y_inc)


def has_passed_target(
    cx: int, cy: int, tx: int, ty: int, x_inc: int, y_inc: int
) -> bool:
    """Return True when the missile has moved past its target.

    Check is done per-axis: if the increment is positive and current
    coordinate ≥ target (or negative and ≤ target) in *either* axis the
    missile has arrived.  Exact precision is not required (matching the
    original hardware behaviour).
    """
    if x_inc > 0 and cx >= tx:
        return True
    if x_inc < 0 and cx <= tx:
        return True
    if y_inc > 0 and cy >= ty:
        return True
    if y_inc < 0 and cy <= ty:
        return True
    return False


# ── ABM (Anti-Ballistic Missile – player) ──────────────────────────────────


@dataclass
class ABM:
    """Player-fired Anti-Ballistic Missile.

    Movement uses the same fixed-point 8.8 increment system as the
    original arcade.  Side silos fire at 3 units/frame; the center silo
    fires at 7 units/frame.

    A maximum of 8 ABMs may be active simultaneously (slot system).
    """

    silo_index: int  # 0 = left, 1 = center, 2 = right
    start_x: int
    start_y: int
    target_x: int
    target_y: int
    # Fixed-point position (8.8)
    current_x_fp: int = 0
    current_y_fp: int = 0
    x_increment: int = 0
    y_increment: int = 0
    is_active: bool = True

    def __post_init__(self) -> None:
        speed = ABM_SPEED_CENTER if self.silo_index == 1 else ABM_SPEED_SIDE
        self.current_x_fp = to_fixed(self.start_x)
        self.current_y_fp = to_fixed(self.start_y)
        self.x_increment, self.y_increment = compute_increments(
            self.start_x, self.start_y,
            self.target_x, self.target_y,
            speed,
        )

    # Convenience integer properties ─────────────────────────────────────
    @property
    def current_x(self) -> int:
        return from_fixed(self.current_x_fp)

    @property
    def current_y(self) -> int:
        return from_fixed(self.current_y_fp)

    @property
    def current_pos(self) -> tuple[int, int]:
        return (self.current_x, self.current_y)

    # Update ──────────────────────────────────────────────────────────────
    def update(self) -> None:
        """Advance the ABM one frame along its trajectory."""
        if not self.is_active:
            return
        self.current_x_fp += self.x_increment
        self.current_y_fp += self.y_increment
        if has_passed_target(
            self.current_x, self.current_y,
            self.target_x, self.target_y,
            self.x_increment, self.y_increment,
        ):
            self.is_active = False

    def deactivate(self) -> None:
        self.is_active = False


# ── ICBM (Incoming missile) ────────────────────────────────────────────────


@dataclass
class ICBM:
    """Enemy Intercontinental Ballistic Missile.

    Uses the same fixed-point increment system as ABMs.  MIRV logic
    follows the original ROM constraints (see $5379/$56d1 for MIRV
    logic):

    - Current or previously examined missile is between altitudes
      128-159
    - No previously examined missile is above altitude 159
    - Available slots in ICBM table
    - Unspent ICBMs remain for the wave
    """

    entry_x: int
    entry_y: int
    target_x: int
    target_y: int
    speed: int = 1
    # Fixed-point position
    current_x_fp: int = 0
    current_y_fp: int = 0
    x_increment: int = 0
    y_increment: int = 0
    can_mirv: bool = False
    has_mirved: bool = False
    is_active: bool = True

    def __post_init__(self) -> None:
        self.current_x_fp = to_fixed(self.entry_x)
        self.current_y_fp = to_fixed(self.entry_y)
        self.x_increment, self.y_increment = compute_increments(
            self.entry_x, self.entry_y,
            self.target_x, self.target_y,
            self.speed,
        )

    @property
    def current_x(self) -> int:
        return from_fixed(self.current_x_fp)

    @property
    def current_y(self) -> int:
        return from_fixed(self.current_y_fp)

    @property
    def altitude(self) -> int:
        """Altitude is the Y screen coordinate (top = 0)."""
        return self.current_y

    @property
    def current_pos(self) -> tuple[int, int]:
        return (self.current_x, self.current_y)

    def update(self) -> None:
        """Advance the ICBM one frame."""
        if not self.is_active:
            return
        self.current_x_fp += self.x_increment
        self.current_y_fp += self.y_increment
        if has_passed_target(
            self.current_x, self.current_y,
            self.target_x, self.target_y,
            self.x_increment, self.y_increment,
        ):
            self.is_active = False

    def deactivate(self) -> None:
        self.is_active = False

    # MIRV ────────────────────────────────────────────────────────────────

    @staticmethod
    def check_mirv_conditions(
        icbm: "ICBM",
        active_icbm_count: int,
        remaining_wave_icbms: int,
        any_above_high: bool,
    ) -> bool:
        """Return True if *icbm* may split (MIRV).

        Conditions (see $56d1):
        1. Missile altitude is in range [MIRV_ALTITUDE_LOW, MIRV_ALTITUDE_HIGH].
        2. No previously examined missile is above MIRV_ALTITUDE_HIGH
           (i.e. lower Y value means higher on screen).
        3. Slots available in the ICBM table (< MAX_ICBM_SLOTS).
        4. Unspent ICBMs remain for the wave.
        5. Missile has not already MIRVed.
        """
        if icbm.has_mirved or not icbm.can_mirv:
            return False
        alt = icbm.altitude
        if not (MIRV_ALTITUDE_LOW <= alt <= MIRV_ALTITUDE_HIGH):
            return False
        if any_above_high:
            return False
        if active_icbm_count >= MAX_ICBM_SLOTS:
            return False
        if remaining_wave_icbms <= 0:
            return False
        return True

    def mirv(
        self,
        targets: list[tuple[int, int]],
        active_icbm_count: int,
        remaining_wave_icbms: int,
    ) -> list["ICBM"]:
        """Attempt to split into up to MIRV_MAX_CHILDREN new ICBMs.

        Returns a list of newly created ICBMs (may be empty).
        """
        children: list[ICBM] = []
        num = min(
            MIRV_MAX_CHILDREN,
            MAX_ICBM_SLOTS - active_icbm_count,
            remaining_wave_icbms,
            len(targets),
        )
        for i in range(num):
            child = ICBM(
                entry_x=self.current_x,
                entry_y=self.current_y,
                target_x=targets[i][0],
                target_y=targets[i][1],
                speed=self.speed,
                can_mirv=False,
            )
            children.append(child)
        self.has_mirved = True
        return children


# ── SmartBomb ───────────────────────────────────────────────────────────────


@dataclass
class SmartBomb(ICBM):
    """Smart bomb – extends ICBM with evasive movement.

    When an explosion is detected nearby the smart bomb switches to a
    table-driven evasion routine that moves toward the target without
    moving closer to the explosion.  Counts as 2 missiles in
    calculations.  Maximum 2 smart bombs on screen.

    Collision detection reads screen pixels looking for flashing colours
    #4/#5.
    """

    evasion_active: bool = False
    nearby_explosions: list[tuple[int, int]] = field(default_factory=list)

    def detect_explosions(
        self, explosion_centers: list[tuple[int, int]]
    ) -> None:
        """Update the list of nearby explosion centres."""
        self.nearby_explosions = list(explosion_centers)
        self.evasion_active = len(self.nearby_explosions) > 0

    def update(self) -> None:
        """Advance one frame, applying evasion if needed."""
        if not self.is_active:
            return
        if self.evasion_active and self.nearby_explosions:
            self._evade()
        else:
            super().update()

    def _evade(self) -> None:
        """Table-driven evasion: move toward target without
        approaching the nearest explosion."""
        # Compute normal increment toward target
        dx_target = self.target_x - self.current_x
        dy_target = self.target_y - self.current_y

        # Find the closest explosion
        closest = self.nearby_explosions[0]
        best_dist = distance_approx(
            self.current_x, self.current_y, closest[0], closest[1]
        )
        for ec in self.nearby_explosions[1:]:
            d = distance_approx(
                self.current_x, self.current_y, ec[0], ec[1]
            )
            if d < best_dist:
                best_dist = d
                closest = ec

        dx_expl = closest[0] - self.current_x
        dy_expl = closest[1] - self.current_y

        # Choose axis movement that does not reduce distance to explosion
        step_x = self.x_increment
        step_y = self.y_increment

        # If moving in X would bring us closer to explosion, zero it
        if dx_expl != 0 and (step_x > 0) == (dx_expl > 0):
            step_x = 0
        if dy_expl != 0 and (step_y > 0) == (dy_expl > 0):
            step_y = 0

        self.current_x_fp += step_x
        self.current_y_fp += step_y

        if has_passed_target(
            self.current_x, self.current_y,
            self.target_x, self.target_y,
            self.x_increment, self.y_increment,
        ):
            self.is_active = False


# ── Flier (Bomber / Satellite) ─────────────────────────────────────────────


class FlierType(Enum):
    BOMBER = auto()
    SATELLITE = auto()


@dataclass
class Flier:
    """Bomber or Satellite that crosses the screen horizontally.

    Travels at mid-screen altitude and can fire multiple missiles at
    once.  Has resurrection and firing cooldowns that decrease on later
    waves.
    """

    flier_type: FlierType
    altitude: int
    direction: int  # +1 = right, -1 = left
    speed: int
    resurrection_timer: int
    firing_timer: int
    current_x: int = 0
    can_fire: bool = True
    is_active: bool = True

    @staticmethod
    def create_random(
        wave_number: int,
        screen_width: int = 256,
        altitude: int = 115,
    ) -> "Flier":
        """Factory: create a random Bomber or Satellite."""
        ft = random.choice([FlierType.BOMBER, FlierType.SATELLITE])
        direction = random.choice([-1, 1])
        start_x = 0 if direction == 1 else screen_width - 1
        speed = 1
        res_timer = max(60 - wave_number * 5, 10)
        fire_timer = max(30 - wave_number * 3, 5)
        return Flier(
            flier_type=ft,
            altitude=altitude,
            direction=direction,
            speed=speed,
            resurrection_timer=res_timer,
            firing_timer=fire_timer,
            current_x=start_x,
        )

    @property
    def current_pos(self) -> tuple[int, int]:
        return (self.current_x, self.altitude)

    def update(self) -> None:
        """Move the flier one frame horizontally."""
        if not self.is_active:
            return
        self.current_x += self.speed * self.direction

    def fire(
        self,
        targets: list[tuple[int, int]],
        speed: int = 1,
    ) -> list[ICBM]:
        """Fire missiles downward toward *targets*."""
        missiles: list[ICBM] = []
        if not self.can_fire or not self.is_active:
            return missiles
        for t in targets:
            missiles.append(
                ICBM(
                    entry_x=self.current_x,
                    entry_y=self.altitude,
                    target_x=t[0],
                    target_y=t[1],
                    speed=speed,
                )
            )
        return missiles

    def deactivate(self) -> None:
        self.is_active = False


# ── Slot Manager ────────────────────────────────────────────────────────────


@dataclass
class MissileSlotManager:
    """Manages the fixed-size slot tables for all missile types.

    Enforces the original hardware limits:
    - 8 ABM slots
    - 8 ICBM/bomb slots
    - 1 flier slot
    """

    abm_slots: list[Optional[ABM]] = field(default_factory=lambda: [None] * MAX_ABM_SLOTS)
    icbm_slots: list[Optional[ICBM]] = field(default_factory=lambda: [None] * MAX_ICBM_SLOTS)
    flier_slot: Optional[Flier] = None

    # ABM management ──────────────────────────────────────────────────────

    @property
    def active_abm_count(self) -> int:
        return sum(1 for s in self.abm_slots if s is not None and s.is_active)

    def add_abm(self, abm: ABM) -> bool:
        """Try to place *abm* into a free slot.  Returns False if full."""
        for i, slot in enumerate(self.abm_slots):
            if slot is None or not slot.is_active:
                self.abm_slots[i] = abm
                return True
        return False

    # ICBM management ─────────────────────────────────────────────────────

    @property
    def active_icbm_count(self) -> int:
        return sum(1 for s in self.icbm_slots if s is not None and s.is_active)

    @property
    def smart_bomb_count(self) -> int:
        return sum(
            1 for s in self.icbm_slots
            if isinstance(s, SmartBomb) and s.is_active
        )

    def add_icbm(self, icbm: ICBM) -> bool:
        """Try to place *icbm* into a free slot.  Returns False if full."""
        if isinstance(icbm, SmartBomb) and self.smart_bomb_count >= MAX_SMART_BOMBS:
            return False
        for i, slot in enumerate(self.icbm_slots):
            if slot is None or not slot.is_active:
                self.icbm_slots[i] = icbm
                return True
        return False

    # Flier management ────────────────────────────────────────────────────

    def set_flier(self, flier: Flier) -> bool:
        if self.flier_slot is not None and self.flier_slot.is_active:
            return False
        self.flier_slot = flier
        return True

    # Bulk operations ─────────────────────────────────────────────────────

    def update_all(self) -> None:
        """Update every active missile / flier."""
        for abm in self.abm_slots:
            if abm is not None and abm.is_active:
                abm.update()
        for icbm in self.icbm_slots:
            if icbm is not None and icbm.is_active:
                icbm.update()
        if self.flier_slot is not None and self.flier_slot.is_active:
            self.flier_slot.update()

    def clear_inactive(self) -> None:
        """Nil-out slots whose occupants have deactivated."""
        for i, abm in enumerate(self.abm_slots):
            if abm is not None and not abm.is_active:
                self.abm_slots[i] = None
        for i, icbm in enumerate(self.icbm_slots):
            if icbm is not None and not icbm.is_active:
                self.icbm_slots[i] = None
        if self.flier_slot is not None and not self.flier_slot.is_active:
            self.flier_slot = None

    def reset(self) -> None:
        """Clear all slots (wave reset)."""
        self.abm_slots = [None] * MAX_ABM_SLOTS
        self.icbm_slots = [None] * MAX_ICBM_SLOTS
        self.flier_slot = None
