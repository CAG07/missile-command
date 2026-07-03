"""
Renderer for Missile Command.

Draws every frame onto a native 256x231 surface (matching the original
arcade's resolution), which is then integer-upscaled onto the actual
application window, centered with pillarboxing/letterboxing when the
window's aspect ratio doesn't match.

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
    GROUND_Y,
    MAX_ABM_SLOTS,
    MAX_ICBM_SLOTS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SILO_CAPACITY,
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
        self._draw_ground(palette)
        self._draw_cities(game, palette)
        self._draw_silos(game, palette)
        self._draw_missiles(game, palette)
        self._draw_explosions(game, frame_count)
        if game.state == GameState.RUNNING:
            self._draw_crosshair(crosshair_pos, frame_count)
        self._draw_hud(game, palette)
        if debug:
            self._draw_debug(game)

    def _draw_ground(self, palette: Palette) -> None:
        pygame.draw.rect(
            self.native, palette.ground,
            (0, GROUND_Y, SCREEN_WIDTH, SCREEN_HEIGHT - GROUND_Y),
        )

    def _draw_cities(self, game: Game, palette: Palette) -> None:
        for city in game.cities.cities:
            x, y = city.position
            if city.is_destroyed:
                pygame.draw.rect(self.native, palette.city_destroyed, (x - 6, y - 2, 12, 4))
            else:
                pygame.draw.rect(self.native, palette.city, (x - 6, y - 6, 12, 8))
                pygame.draw.rect(self.native, palette.city, (x - 4, y - 10, 3, 4))
                pygame.draw.rect(self.native, palette.city, (x + 1, y - 10, 3, 4))

    def _draw_silos(self, game: Game, palette: Palette) -> None:
        for silo in game.defenses.silos:
            x, y = silo.position
            if silo.is_destroyed:
                pygame.draw.rect(self.native, palette.city_destroyed, (x - 6, y - 2, 12, 4))
                continue
            pygame.draw.polygon(
                self.native, palette.silo,
                [(x - 6, y + 2), (x + 6, y + 2), (x, y - 8)],
            )
            self._draw_ammo_pips(x, y, silo.abm_count, palette)

    def _draw_ammo_pips(self, x: int, y: int, count: int, palette: Palette) -> None:
        pip_color = palette.silo
        if count <= 0:
            pip_color = (200, 40, 40)
        elif count <= 3:
            pip_color = (240, 200, 40)
        for i in range(min(count, SILO_CAPACITY)):
            px = x - 9 + (i % 5) * 4
            py = y + 6 + (i // 5) * 3
            pygame.draw.rect(self.native, pip_color, (px, py, 2, 2))

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
            color = (255, 210, 60) if isinstance(missile, SmartBomb) else palette.icbm_trail
            pygame.draw.line(
                self.native, color,
                (missile.entry_x, missile.entry_y), missile.current_pos,
            )
            pygame.draw.circle(self.native, (255, 255, 255), missile.current_pos, 1)

        flier = game.missiles.flier_slot
        if flier is not None and flier.is_active:
            self._draw_flier(flier, palette)

    def _draw_flier(self, flier: Flier, palette: Palette) -> None:
        x, y = flier.current_pos
        w = 5 if flier.direction > 0 else -5
        pygame.draw.polygon(
            self.native, palette.icbm_trail,
            [(x - w, y), (x + w, y - 2), (x + w, y + 2)],
        )

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
