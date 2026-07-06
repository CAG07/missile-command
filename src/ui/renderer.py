"""
Renderer for Missile Command.

Draws every frame onto a native SCREEN_WIDTH×SCREEN_HEIGHT surface (see src.config),
which is then integer-upscaled onto the actual application window, centered
with pillarboxing/letterboxing when the window's aspect ratio doesn't match.

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import pygame

from src.config import (
    GROUND_CRATER_RADIUS,
    GROUND_Y,
    MAX_ABM_SLOTS,
    MAX_ICBM_SLOTS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SILO_CAPACITY,
    SILO_LOW_THRESHOLD,
)
from src.game import Game, GameState
from src.models.explosion import octagon_points
from src.models.missile import Flier, SmartBomb
from src.ui.palette import Palette, explosion_color, flash_color, get_palette

NATIVE_SIZE = (SCREEN_WIDTH, SCREEN_HEIGHT)
FONT_PATH = os.path.join("data", "fnt", "PressStart2P-Regular.ttf")

_font_cache: dict[int, pygame.font.Font] = {}


def get_font(size: int) -> pygame.font.Font:
    """Return a cached font at *size*, falling back to the default font."""
    if size in _font_cache:
        return _font_cache[size]
    try:
        if os.path.isfile(FONT_PATH):
            font = pygame.font.Font(FONT_PATH, size)
        else:
            font = pygame.font.Font(None, size)
    except Exception:
        font = pygame.font.Font(None, size)
    _font_cache[size] = font
    return font


@dataclass
class Renderer:
    """Owns the native render surface and the scaled application window."""

    scale: int = 3
    fullscreen: bool = False

    native: pygame.Surface = field(init=False, repr=False)
    window: Optional[pygame.Surface] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.native = pygame.Surface(NATIVE_SIZE)

    # ── Window management ────────────────────────────────────────────────

    def create_window(self) -> pygame.Surface:
        """Create (or recreate) the application window."""
        if self.fullscreen:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            size = (SCREEN_WIDTH * self.scale, SCREEN_HEIGHT * self.scale)
            self.window = pygame.display.set_mode(size)
        pygame.display.set_caption("Missile Command")
        return self.window

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        self.create_window()

    @property
    def effective_scale(self) -> int:
        """Return the current integer upscale factor in effect."""
        _, _, scaled_w, _ = self._viewport()
        return max(1, scaled_w // SCREEN_WIDTH)

    # ── Coordinate mapping ────────────────────────────────────────────────

    def _viewport(self) -> tuple[int, int, int, int]:
        """Return (x_offset, y_offset, scaled_w, scaled_h) of the native
        surface's destination rect within the current window."""
        if self.window is None:
            return (0, 0, SCREEN_WIDTH * self.scale, SCREEN_HEIGHT * self.scale)
        win_w, win_h = self.window.get_size()
        eff_scale = max(1, min(win_w // SCREEN_WIDTH, win_h // SCREEN_HEIGHT))
        scaled_w = SCREEN_WIDTH * eff_scale
        scaled_h = SCREEN_HEIGHT * eff_scale
        x_off = (win_w - scaled_w) // 2
        y_off = (win_h - scaled_h) // 2
        return (x_off, y_off, scaled_w, scaled_h)

    def window_to_native(self, pos: tuple[int, int]) -> Optional[tuple[int, int]]:
        """Map a window-space position to native coordinates.

        Returns None if *pos* falls within the pillarbox/letterbox bars.
        """
        x_off, y_off, scaled_w, scaled_h = self._viewport()
        wx, wy = pos
        if wx < x_off or wy < y_off or wx >= x_off + scaled_w or wy >= y_off + scaled_h:
            return None
        eff_scale = scaled_w // SCREEN_WIDTH
        if eff_scale <= 0:
            return None
        nx = (wx - x_off) // eff_scale
        ny = (wy - y_off) // eff_scale
        return (
            max(0, min(SCREEN_WIDTH - 1, nx)),
            max(0, min(SCREEN_HEIGHT - 1, ny)),
        )

    # ── Present ───────────────────────────────────────────────────────────

    def present(self) -> None:
        """Upscale the native surface onto the window and flip."""
        if self.window is None:
            return
        x_off, y_off, scaled_w, scaled_h = self._viewport()
        scaled = pygame.transform.scale(self.native, (scaled_w, scaled_h))
        self.window.fill((0, 0, 0))
        self.window.blit(scaled, (x_off, y_off))
        pygame.display.flip()

    # ── Drawing ───────────────────────────────────────────────────────────

    def draw_frame(
        self,
        game: Game,
        crosshair_pos: tuple[int, int],
        frame_count: int,
        debug: bool = False,
    ) -> None:
        """Draw one full frame of gameplay onto the native surface."""
        palette = get_palette(game.wave_number)
        self.native.fill(palette.sky)
        self._draw_ground(game, palette)
        self._draw_cities(game, palette)
        self._draw_silos(game, palette)
        self._draw_missiles(game, palette)
        self._draw_explosions(game, frame_count)
        if game.state == GameState.RUNNING:
            self._draw_crosshair(crosshair_pos, frame_count)
        self._draw_hud(game, palette)
        if debug:
            self._draw_debug(game)

    #: City tuft cluster: a small, low, bushy cluster of spikes whose
    #: base sits exactly on the ground line. Kept narrow so the 6 cities
    #: fit cleanly between the 3 silo mounds without overlapping them.
    _CITY_TUFT_HEIGHTS = (5, 8, 6, 8, 5)
    _CITY_TUFT_SPREAD = 8

    #: Silo mound: a wide, low, flat-topped plateau that the ammo rockets
    #: stand on in a triangular pyramid (see Screenshot 2026-07-04 093456).
    _SILO_MOUND_HALF_WIDTH = 12
    _SILO_MOUND_TOP_HALF_WIDTH = 7
    _SILO_MOUND_HEIGHT = 9

    #: Row sizes (top to bottom) forming a 10-missile triangular pyramid,
    #: matching SILO_CAPACITY. Filled top-down as ammo count increases.
    _AMMO_PYRAMID_ROWS = (1, 2, 3, 4)

    def _draw_ground(self, game: Game, palette: Palette) -> None:
        """Flat ground band with a flat-topped mound under each silo."""
        pygame.draw.rect(
            self.native, palette.ground,
            (0, GROUND_Y, SCREEN_WIDTH, SCREEN_HEIGHT - GROUND_Y),
        )
        for x in game.ground_craters:
            self._draw_ground_crater(x, palette)
        for silo in game.defenses.silos:
            self._draw_silo_mound(silo.position_x, palette, silo.is_destroyed)

    def _draw_ground_crater(self, cx: int, palette: Palette) -> None:
        """A permanent wedge bitten out of the ground line by an
        explosion that touched down there -- whether or not it
        destroyed a city/silo, matching the original arcade's
        persistent terrain scarring."""
        r = GROUND_CRATER_RADIUS
        pygame.draw.polygon(
            self.native, palette.sky,
            [(cx - r, GROUND_Y), (cx + r, GROUND_Y), (cx, GROUND_Y + r)],
        )

    def _draw_silo_mound(self, cx: int, palette: Palette, destroyed: bool = False) -> None:
        """Raised flat-topped plateau the silo's ammo rockets stand on.

        Scorched/blackened when the silo is destroyed, so the wreckage
        is visible at a glance instead of the mound looking untouched.
        """
        hw = self._SILO_MOUND_HALF_WIDTH
        top_hw = self._SILO_MOUND_TOP_HALF_WIDTH
        h = self._SILO_MOUND_HEIGHT
        color = palette.city_destroyed if destroyed else palette.ground
        pygame.draw.polygon(
            self.native, color,
            [
                (cx - hw, GROUND_Y), (cx - top_hw, GROUND_Y - h),
                (cx + top_hw, GROUND_Y - h), (cx + hw, GROUND_Y),
            ],
        )

    #: Collapsed-rubble silhouette heights for a destroyed city -- same
    #: footprint as an intact city (_CITY_TUFT_HEIGHTS) but crushed down
    #: to read clearly as "flattened", not just recolored.
    _CITY_RUBBLE_HEIGHTS = (2, 4, 2, 4, 2)

    def _draw_cities(self, game: Game, palette: Palette) -> None:
        for city in game.cities.cities:
            x, _ = city.position
            if city.is_destroyed:
                self._draw_spiky_cluster(
                    x, GROUND_Y, palette.city_destroyed,
                    self._CITY_TUFT_SPREAD, self._CITY_RUBBLE_HEIGHTS,
                )
            else:
                self._draw_spiky_cluster(
                    x, GROUND_Y, palette.city, self._CITY_TUFT_SPREAD, self._CITY_TUFT_HEIGHTS,
                )

    #: Baseline Y and horizontal spacing for the wave-end city tally row --
    #: a dedicated, undamaged city icon per surviving city, kept separate
    #: from the real battlefield (which may still show nearby scorching
    #: even for a city that survived the wave).
    _CITY_TALLY_ROW_Y = 108
    _CITY_TALLY_ROW_SPACING = 20

    def draw_city_tally_row(self, total: int, revealed: int) -> None:
        """Draw a row of clean city icons across the screen, revealing
        them left-to-right one at a time as the wave-end tally counts up
        surviving cities (synced to the roll_up_2 tick sound)."""
        if total <= 0:
            return
        spacing = self._CITY_TALLY_ROW_SPACING
        start_x = SCREEN_WIDTH // 2 - (spacing * (total - 1)) // 2
        for i in range(total):
            x = start_x + i * spacing
            if i < revealed:
                self._draw_spiky_cluster(
                    x, self._CITY_TALLY_ROW_Y, (255, 220, 0),
                    self._CITY_TUFT_SPREAD, self._CITY_TUFT_HEIGHTS,
                )
            else:
                pygame.draw.circle(self.native, (70, 70, 70), (x, self._CITY_TALLY_ROW_Y), 1)

    def _draw_spiky_cluster(
        self, cx: int, base_y: int, color, spread: int, heights: tuple[int, ...],
    ) -> None:
        """Draw a small cluster of jagged spikes (city rubble tufts)."""
        n = len(heights)
        start_x = cx - spread // 2
        step = max(1, spread // n)
        for i, h in enumerate(heights):
            x = start_x + i * step
            pygame.draw.polygon(
                self.native, color,
                [(x - 2, base_y), (x, base_y - h), (x + 2, base_y)],
            )

    def _draw_silos(self, game: Game, palette: Palette) -> None:
        for silo in game.defenses.silos:
            x, _ = silo.position
            top_y = GROUND_Y - self._SILO_MOUND_HEIGHT
            if silo.is_destroyed:
                # Mound is already darkened by _draw_silo_mound; mark the
                # wreckage with a bright X so an empty-but-intact silo
                # (0 ABMs left) is never confused with a destroyed one.
                pygame.draw.line(
                    self.native, (255, 255, 255),
                    (x - 5, top_y - 4), (x + 5, top_y + 2), 1,
                )
                pygame.draw.line(
                    self.native, (255, 255, 255),
                    (x - 5, top_y + 2), (x + 5, top_y - 4), 1,
                )
                continue
            self._draw_ammo_rockets(x, top_y, silo.abm_count, palette)

    def _draw_ammo_rockets(self, cx: int, top_y: int, count: int, palette: Palette) -> None:
        """Draw remaining ABMs as a triangular pyramid of rocket icons
        standing on the mound's flat top -- one icon per remaining ABM,
        up to the full 10-missile pyramid at SILO_CAPACITY. Always drawn
        in the silo's normal color; low ammo is signalled only by the
        "LOW"/"OUT" HUD banner, not by recoloring the icons."""
        if count <= 0:
            return
        color = palette.silo
        n = min(count, SILO_CAPACITY)
        icon_spacing_x = 4
        row_spacing_y = 3
        drawn = 0
        for row_i, row_size in enumerate(self._AMMO_PYRAMID_ROWS):
            if drawn >= n:
                break
            y = top_y + row_i * row_spacing_y
            row_width = (row_size - 1) * icon_spacing_x
            start_x = cx - row_width // 2
            for slot in range(row_size):
                if drawn >= n:
                    break
                x = start_x + slot * icon_spacing_x
                self._draw_rocket_icon(x, y, height=3, color=color)
                drawn += 1

    def _draw_rocket_icon(self, x: int, base_y: int, height: int, color) -> None:
        """A tiny rocket silhouette: a short body with a small forked base."""
        pygame.draw.line(self.native, color, (x, base_y), (x, base_y - height))
        pygame.draw.line(self.native, color, (x, base_y), (x - 1, base_y + 1))
        pygame.draw.line(self.native, color, (x, base_y), (x + 1, base_y + 1))

    #: Bright green, verified distinct from every color in every wave
    #: palette (city/silo/abm_trail/icbm_trail) so smart bombs always
    #: read as visually different from regular ICBMs.
    _SMART_BOMB_COLOR = (50, 255, 50)

    def _draw_missiles(self, game: Game, palette: Palette) -> None:
        for abm in game.missiles.abm_slots:
            if abm is not None and abm.is_active:
                pygame.draw.line(
                    self.native, palette.abm_trail,
                    (abm.start_x, abm.start_y), abm.current_pos,
                )
                pygame.draw.circle(self.native, (255, 255, 255), abm.current_pos, 1)

        for missile in game.missiles.icbm_slots:
            if missile is None or not missile.is_active:
                continue
            # A fixed color here previously collided exactly with
            # PALETTES[2].icbm_trail (255, 210, 60) on waves 3/7/11/...,
            # making smart bombs indistinguishable from regular ICBMs.
            # Bright green doesn't appear in any wave palette's colors.
            color = self._SMART_BOMB_COLOR if isinstance(missile, SmartBomb) else palette.icbm_trail
            pygame.draw.line(
                self.native, color,
                (missile.entry_x, missile.entry_y), missile.current_pos,
            )
            pygame.draw.circle(self.native, (255, 255, 255), missile.current_pos, 1)

        flier = game.missiles.flier_slot
        if flier is not None and flier.is_active:
            self._draw_flier(flier, palette)

    #: Side-view jet silhouette (pointed nose, flat canopy top, vertical
    #: tail fin, single swept wing below the fuselage) for a flier
    #: facing right (+x); mirrored in X for direction < 0. A side-view
    #: reads as "airplane" more clearly than a symmetric top-down dart
    #: at the small pixel sizes this sprite renders at.
    _FLIER_SHAPE_RIGHT_FACING = (
        (7, 0), (2, -1), (-4, -1), (-6, -3),
        (-7, 0), (-3, 4), (1, 1),
    )

    def _draw_flier(self, flier: Flier, palette: Palette) -> None:
        cx, cy = flier.current_pos
        mirror = 1 if flier.direction > 0 else -1
        points = [(cx + mirror * dx, cy + dy) for dx, dy in self._FLIER_SHAPE_RIGHT_FACING]
        pygame.draw.polygon(self.native, palette.icbm_trail, points)

    def _draw_explosions(self, game: Game, frame_count: int) -> None:
        color = explosion_color(frame_count)
        for exp in game.explosions.slots:
            if exp is not None and exp.is_active and exp.current_radius > 0:
                pygame.draw.polygon(self.native, color, exp.get_octagon_points())

    def _draw_crosshair(self, pos: tuple[int, int], frame_count: int) -> None:
        x, y = pos
        y = min(y, GROUND_Y - 1)
        color = flash_color(frame_count)
        pygame.draw.line(self.native, color, (x - 4, y), (x + 4, y))
        pygame.draw.line(self.native, color, (x, y - 4), (x, y + 4))

    def _draw_hud(self, game: Game, palette: Palette) -> None:
        font = get_font(7)
        score_surf = font.render(game.score_display.format_score(), True, palette.text)
        self.native.blit(score_surf, (4, 2))
        high_surf = font.render(game.score_display.format_high_score(), True, palette.text)
        self.native.blit(high_surf, (SCREEN_WIDTH - high_surf.get_width() - 4, 2))
        wave_surf = font.render(f"WAVE {game.wave_number}", True, palette.text)
        self.native.blit(wave_surf, (SCREEN_WIDTH // 2 - wave_surf.get_width() // 2, 2))
        self._draw_ammo_status_banner(game, palette)

    def _draw_ammo_status_banner(self, game: Game, palette: Palette) -> None:
        """'OUT'/'LOW' text banner at bottom-center, per the arcade HUD."""
        if game.state != GameState.RUNNING:
            return
        counts = [s.abm_count for s in game.defenses.silos if not s.is_destroyed]
        if not counts:
            return
        lowest = min(counts)
        if lowest <= 0:
            text = "OUT"
        elif lowest <= SILO_LOW_THRESHOLD:
            text = "LOW"
        else:
            return
        surf = get_font(8).render(text, True, (60, 90, 230))
        self.native.blit(surf, (SCREEN_WIDTH // 2 - surf.get_width() // 2, GROUND_Y + 1))

    def _draw_debug(self, game: Game) -> None:
        font = get_font(7)
        texts = [
            f"ABM {game.missiles.active_abm_count}/{MAX_ABM_SLOTS}",
            f"ICBM {game.missiles.active_icbm_count}/{MAX_ICBM_SLOTS}",
            f"EXP {game.explosions.active_count}",
            f"ICBMs left {game.icbms_remaining_this_wave}",
        ]
        y = 14
        for text in texts:
            surf = font.render(text, True, (0, 255, 0))
            self.native.blit(surf, (4, y))
            y += 9

    # ── Game over: "THE END" ──────────────────────────────────────────────

    #: Frame (relative to draw_the_end's frame_count) at which the
    #: expanding octagon first reaches max_radius -- this is when the
    #: hidden-face easter egg flashes, homaging the original arcade
    #: game's famous accidental "face in the mushroom cloud" that's
    #: only ever visible for a handful of frames.
    _FACE_FLASH_START = 50
    _FACE_FLASH_FRAMES = 6

    def draw_the_end(self, frame_count: int) -> None:
        """Draw the expanding octagonal "THE END" game-over screen.

        A yellow octagon expands from the center over ~1.5s, then a
        red "THE END" caption fades in once it's large enough to
        contain the text, over the ruined (already-drawn) landscape.
        Right as the octagon reaches full size, a hidden face flashes
        briefly inside it (see _draw_hidden_face).
        """
        max_radius = 150
        radius = min(max_radius, frame_count * 3)
        cx, cy = SCREEN_WIDTH // 2, (GROUND_Y // 2)
        if radius > 0:
            pygame.draw.polygon(self.native, (235, 205, 40), octagon_points(cx, cy, radius))
        if radius >= max_radius * 0.5:
            font = get_font(16)
            surf = font.render("THE END", True, (200, 30, 30))
            x = cx - surf.get_width() // 2
            y = cy - surf.get_height() // 2
            self.native.blit(surf, (x, y))
        if (
            self._FACE_FLASH_START
            <= frame_count
            < self._FACE_FLASH_START + self._FACE_FLASH_FRAMES
        ):
            self._draw_hidden_face(cx, cy, radius)

    def _draw_hidden_face(self, cx: int, cy: int, radius: int) -> None:
        """Flash a small face inside the fully-expanded octagon.

        Sized and positioned relative to *radius* so it stays inside
        the octagon's bounds.
        """
        eye_dx = radius // 3
        eye_dy = -radius // 6
        eye_r = max(2, radius // 12)
        color = (20, 20, 20)
        pygame.draw.circle(self.native, color, (cx - eye_dx, cy + eye_dy), eye_r)
        pygame.draw.circle(self.native, color, (cx + eye_dx, cy + eye_dy), eye_r)
        mouth_y = cy + radius // 4
        mouth_half_w = radius // 3
        pygame.draw.arc(
            self.native, color,
            (cx - mouth_half_w, mouth_y - radius // 6, mouth_half_w * 2, radius // 3),
            3.4, 6.03,
            max(2, radius // 20),
        )
