"""
Configuration constants for Missile Command.

Based on the original Atari arcade hardware specifications.
See Missile Command Disassembly.pdf for technical reference.
"""

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
SCREEN_WIDTH: int = 256
SCREEN_HEIGHT: int = 231
UPDATE_RATE: int = 60  # Hz – all timing assumes 60 fps

# ---------------------------------------------------------------------------
# Slot limits (mirroring the original hardware tables)
# ---------------------------------------------------------------------------
MAX_ABM_SLOTS: int = 8       # ABM missile table size
MAX_ICBM_SLOTS: int = 8      # ICBM / bomb table size
MAX_FLIER_SLOTS: int = 1     # only one flier at a time
MAX_EXPLOSION_SLOTS: int = 20  # 5 groups × 4 slots
EXPLOSION_GROUPS: int = 5
EXPLOSIONS_PER_GROUP: int = 4

# ---------------------------------------------------------------------------
# ABM (Anti-Ballistic Missile – player missiles)
# ---------------------------------------------------------------------------
ABM_SPEED_SIDE: int = 3   # units per frame for left / right silos
ABM_SPEED_CENTER: int = 7  # units per frame for center silo

# ---------------------------------------------------------------------------
# Silo configuration
# ---------------------------------------------------------------------------
NUM_SILOS: int = 3
SILO_CAPACITY: int = 10  # ABMs per silo at wave start

# Silo X positions (original arcade screen coordinates)
SILO_POSITIONS: list[tuple[int, int]] = [
    (32, 220),    # left silo   (index 0)
    (128, 220),   # center silo (index 1)
    (224, 220),   # right silo  (index 2)
]
SILO_Y: int = 220  # ground-level Y for all silos

# ---------------------------------------------------------------------------
# City configuration
# ---------------------------------------------------------------------------
NUM_CITIES_DEFAULT: int = 6  # marathon-mode default (DIP switch selectable 4-7)
MAX_CITIES_DESTROYED_PER_WAVE: int = 3

# Arcade city positions (X only; Y sits on the ground line)
CITY_POSITIONS: list[tuple[int, int]] = [
    (48, 216),
    (72, 216),
    (96, 216),
    (160, 216),
    (184, 216),
    (208, 216),
]
CITY_Y: int = 216

# ---------------------------------------------------------------------------
# Bonus cities
# ---------------------------------------------------------------------------
BONUS_CITY_POINTS: int = 10_000  # default; DIP-switch selectable 8000-20000

# ---------------------------------------------------------------------------
# Explosion
# ---------------------------------------------------------------------------
EXPLOSION_MAX_RADIUS: int = 13
EXPLOSION_OCTAGON_SLOPE_NUM: int = 3  # numerator of 3/8 slope
EXPLOSION_OCTAGON_SLOPE_DEN: int = 8  # denominator
EXPLOSION_COLLISION_ALTITUDE_MIN: int = 33  # no collision below line 33

# ---------------------------------------------------------------------------
# MIRV altitude thresholds
# ---------------------------------------------------------------------------
MIRV_ALTITUDE_LOW: int = 128
MIRV_ALTITUDE_HIGH: int = 159
MIRV_MAX_CHILDREN: int = 3

# ---------------------------------------------------------------------------
# Flier
# ---------------------------------------------------------------------------
FLIER_ALTITUDE: int = 115  # approximately mid-screen

# ---------------------------------------------------------------------------
# Scoring (per original arcade)
# ---------------------------------------------------------------------------
POINTS_PER_ICBM: int = 25
POINTS_PER_SMART_BOMB: int = 125
POINTS_PER_FLIER: int = 100
POINTS_PER_REMAINING_ABM: int = 5
POINTS_PER_SURVIVING_CITY: int = 100

# ---------------------------------------------------------------------------
# Wave speed table (ICBM speed values by wave number, index 0 = wave 1)
# Speeds increase each wave up to a cap.  Values are in 8.8 fixed-point
# fractional units.  See disassembly for exact per-wave table.
# ---------------------------------------------------------------------------
WAVE_SPEEDS: list[int] = [
    1, 1, 2, 2, 3, 3, 4, 4, 5, 5,
    6, 6, 7, 7, 8, 8, 8, 8, 8, 8,
]

# Attack pacing altitude = 202 - 2 * wave_number, minimum 180
ATTACK_PACE_BASE: int = 202
ATTACK_PACE_FACTOR: int = 2
ATTACK_PACE_MIN: int = 180

# ---------------------------------------------------------------------------
# Smart bomb
# ---------------------------------------------------------------------------
MAX_SMART_BOMBS: int = 2  # max on screen at once

# ---------------------------------------------------------------------------
# Colors (arcade palette indices)
# ---------------------------------------------------------------------------
COLOR_EXPLOSION_FLASH_A: int = 4
COLOR_EXPLOSION_FLASH_B: int = 5

# ---------------------------------------------------------------------------
# Fixed-point math helpers
# ---------------------------------------------------------------------------
FIXED_POINT_SHIFT: int = 8  # 8.8 format
FIXED_POINT_SCALE: int = 1 << FIXED_POINT_SHIFT  # 256
