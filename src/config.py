"""
Configuration constants for Missile Command.

Based on the original Atari arcade hardware specifications.
See Missile Command Disassembly.pdf for technical reference.
"""

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
# The original arcade's native resolution was 256x231 (~1.11:1). Widened
# to a 16:9-ish playfield (410x231) so fullscreen fills modern widescreen
# monitors without pillarboxing, per user request -- silo/city X positions
# below are scaled proportionally from the original layout to fill the
# extra width rather than being stretched.
SCREEN_WIDTH: int = 410
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
SILO_LOW_THRESHOLD: int = 3  # "LOW" HUD indicator / warning at this many left

# Silo X positions, scaled proportionally from the original arcade's
# 256-wide layout (32, 128, 224) to fill the widened 410px playfield.
# Center silo stays exactly at SCREEN_WIDTH // 2.
SILO_POSITIONS: list[tuple[int, int]] = [
    (51, 220),    # left silo   (index 0)
    (205, 220),   # center silo (index 1)
    (359, 220),   # right silo  (index 2)
]
SILO_Y: int = 220  # ground-level Y for all silos

# ---------------------------------------------------------------------------
# City configuration
# ---------------------------------------------------------------------------
NUM_CITIES_DEFAULT: int = 6  # marathon-mode default (DIP switch selectable 4-7)
MAX_CITIES_DESTROYED_PER_WAVE: int = 3

# City X positions, scaled proportionally from the original arcade's
# 256-wide layout to fill the widened 410px playfield (Y sits on ground).
CITY_POSITIONS: list[tuple[int, int]] = [
    (77, 216),
    (115, 216),
    (154, 216),
    (256, 216),
    (295, 216),
    (333, 216),
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

# First wave MIRVs are allowed to appear. The shipped ROM's own check at
# $56d1 compares wave < 1 (always false), a documented off-by-one bug --
# the disassembly's own comment on that line says it "should probably be
# #$02". We implement the intended design (no MIRVs on wave 1), not the
# shipped bug.
MIRV_START_WAVE: int = 2

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
# ICBM "speed" is NOT a velocity -- per the wave guide, it's the number of
# frames the game waits between moving an ICBM at all (0 = moves every
# frame, fastest; higher = longer pause between each 1-unit step). Stored
# internally as an 8.8 fixed-point value added to a per-missile counter.
# When a move *does* happen, it always advances by exactly 1 unit -- the
# whole difficulty ramp comes from how often that happens, not step size.
#
# NOTE: the wave-guide's own literal per-wave values (4.8125, 2.875, 1.75,
# ...) were verified byte-for-byte against the source, but produce a ramp
# that halves roughly every wave (wave 1 -> wave 3 in this game's terms is
# a single ICBM's full-screen fall time going from ~21s to ~10s) -- too
# steep per direct user playtesting feedback, despite matching the
# documented table. Replaced with a deliberately gentler, hand-tuned curve
# per that feedback: wave 1 slower (~40s full-screen fall), and the ramp
# toward "fast" spread across all 15 waves instead of front-loaded into
# the first 8. This is an intentional deviation from the literal
# disassembly values, not a research error -- SPEC.md's "disassembly wins"
# default is overridden here by explicit, repeated user direction after
# hands-on testing.
ICBM_MOVE_DELAY_TABLE: list[float] = [
    9.9, 7.7, 5.8, 4.5, 3.4, 2.5, 1.9, 1.3,
    0.9, 0.6, 0.4, 0.25, 0.15, 0.06, 0.0,
]
ICBM_BASE_STEP_SPEED: int = 1  # units advanced per actual move (constant)

# ICBMs launched per wave (1-indexed by position; wave 20+ reuses the
# last entry). Source: https://6502disassembly.com/va-missile-command/wave-guide.html
ICBM_COUNT_TABLE: list[int] = [
    12, 15, 18, 12, 16, 14, 17, 10, 13, 16,
    19, 12, 14, 16, 18, 14, 17, 19, 22,
]

# Attack pacing altitude = 202 - 2 * wave_number, minimum 180
ATTACK_PACE_BASE: int = 202
ATTACK_PACE_FACTOR: int = 2
ATTACK_PACE_MIN: int = 180

# ---------------------------------------------------------------------------
# Smart bomb
# ---------------------------------------------------------------------------
MAX_SMART_BOMBS: int = 2  # max on screen at once
SMART_BOMB_START_WAVE: int = 6       # first wave smart bombs may appear (wave-guide)
SMART_BOMB_CHANCE: float = 0.2       # chance a paced attack spawn is a smart bomb
SMART_BOMB_EVASION_RADIUS: int = 40  # native-pixel radius that triggers evasion

# ---------------------------------------------------------------------------
# Attack pacing / wave spawning
# ---------------------------------------------------------------------------
ATTACK_BATCH_SIZE: int = 4  # max ICBMs launched in a single pacing check

# ---------------------------------------------------------------------------
# Flier (bomber / satellite) spawning
#
# Per-wave (cooldown_frames, fire_rate_frames, (altitude_min, altitude_max)).
# Fliers first appear in wave 2 ("appear as often as possible"); values
# beyond wave 8 continue unchanged. Bombers move 1px/3 frames, satellites
# 1px/2 frames. Source: https://6502disassembly.com/va-missile-command/wave-guide.html
# ---------------------------------------------------------------------------
FLIER_START_WAVE: int = 2
FLIER_INITIAL_DELAY_FRAMES: int = 300  # ~5s at 60Hz before the first flier
FLIER_WAVE_TABLE: dict[int, tuple[int, int, tuple[int, int]]] = {
    2: (240, 128, (148, 195)),
    3: (160, 96, (148, 195)),
    4: (128, 64, (132, 163)),
    5: (128, 48, (132, 163)),
    6: (96, 32, (100, 131)),
    7: (64, 32, (100, 131)),
    8: (32, 16, (100, 131)),
}
FLIER_BOMBER_MOVE_INTERVAL: int = 3   # 1 pixel every N frames
FLIER_SATELLITE_MOVE_INTERVAL: int = 2  # 1 pixel every N frames

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

# ---------------------------------------------------------------------------
# Rendering / window
# ---------------------------------------------------------------------------
DEFAULT_SCALE: int = 3  # integer upscale factor for the 256x231 native surface
GROUND_Y: int = 220     # native-pixel Y of the ground line
CROSSHAIR_SENSITIVITY: float = 1.0  # trackball-emulation mouse sensitivity

# Ground scarring: any explosion (ABM or ICBM) that visually touches the
# ground line permanently bites a small crater out of the terrain there,
# whether or not it destroyed a city/silo -- matches the original arcade's
# persistent battlefield-scarring look.
GROUND_CRATER_RADIUS: int = 5
MAX_GROUND_CRATERS: int = 60  # oldest craters evicted FIFO beyond this
WAVE_END_DISPLAY_FRAMES: int = 180  # ~3s tally screen before the next wave
GAME_OVER_DISPLAY_FRAMES: int = 120  # ~2s for the "THE END" animation to play
WAVE_INTRO_DISPLAY_FRAMES: int = 90  # ~1.5s "WAVE N" intro before attacks begin
