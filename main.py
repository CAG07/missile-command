"""
Main entry point for Missile Command.

Initializes pygame, sets up the 60Hz game loop, and manages the
overall application lifecycle matching the original arcade's timing.

Usage:
    python missile-defense.py [OPTIONS]

Options:
    --fullscreen         Launch in fullscreen mode
    --scale N            Display scale multiplier (1-4, default: 2)
    --debug              Enable debug overlays
    --attract            Start in attract mode
    --wave N             Start at specific wave (testing)
    --marathon           Marathon mode (default)
    --tournament         Tournament mode (no bonus cities)

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from src.config import SCREEN_WIDTH, SCREEN_HEIGHT, UPDATE_RATE
from src.game import Game, GameState
from src.ui.audio import AudioManager, SoundEvent
from src.ui.high_scores import (
    load_scores, save_high_scores, update_high_scores, get_top_score,
    check_high_score,
)


# ── Constants ───────────────────────────────────────────────────────────────

FRAME_TIME: float = 1.0 / UPDATE_RATE          # ~16.67 ms
IRQ_PER_FRAME: int = 4                          # 240 Hz / 60 Hz
COLOR_CYCLE_IRQS: int = 8                       # 30 Hz color cycling

DEFAULT_SCALE: int = 2
MIN_SCALE: int = 1
MAX_SCALE: int = 4


# ── Argument parsing ───────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Missile Command – arcade-faithful recreation",
    )
    parser.add_argument(
        "--fullscreen", action="store_true",
        help="Launch in fullscreen mode",
    )
    parser.add_argument(
        "--scale", type=int, default=DEFAULT_SCALE,
        choices=range(MIN_SCALE, MAX_SCALE + 1),
        metavar="N",
        help=f"Display scale multiplier ({MIN_SCALE}-{MAX_SCALE}, default: {DEFAULT_SCALE})",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug overlays (FPS, slots, collision boxes)",
    )
    parser.add_argument(
        "--attract", action="store_true",
        help="Start in attract mode",
    )
    parser.add_argument(
        "--wave", type=int, default=1,
        metavar="N",
        help="Start at specific wave (for testing)",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--marathon", action="store_true", default=True,
        help="Marathon mode (default)",
    )
    mode_group.add_argument(
        "--tournament", action="store_true",
        help="Tournament mode (no bonus cities)",
    )
    return parser.parse_args(argv)


# ── Application ─────────────────────────────────────────────────────────────


@dataclass
class MissileCommandApp:
    """Top-level application wrapper.

    Owns the pygame display, game state, and main loop.
    """

    scale: int = DEFAULT_SCALE
    fullscreen: bool = False
    debug: bool = False
    start_wave: int = 1
    tournament: bool = False

    # Runtime state (initialized in ``init``)
    screen: object = field(default=None, repr=False)
    clock: object = field(default=None, repr=False)
    game: Game = field(default_factory=Game)
    running: bool = False

    # IRQ simulation
    irq_counter: int = 0
    color_cycle_counter: int = 0

    # Crosshair position (game coordinates, for keyboard control)
    crosshair_x: int = SCREEN_WIDTH // 2
    crosshair_y: int = SCREEN_HEIGHT // 2
    crosshair_speed: int = 3  # pixels per frame at game resolution

    # Performance tracking
    frame_times: list[float] = field(default_factory=list)
    fps: float = 0.0
    defer_score_redraw: bool = False

    # Audio
    audio: AudioManager = field(default_factory=AudioManager)

    # High scores
    high_scores: dict = field(default_factory=dict)
    scores_file: str = "scores.json"
    _prev_state: GameState = GameState.ATTRACT

    # ── Initialisation ──────────────────────────────────────────────────

    def init(self) -> bool:
        """Initialise pygame and create the display surface.

        Returns True on success, False on failure.
        """
        if pygame is None:
            print("Error: pygame is required. Install with: pip install pygame",
                  file=sys.stderr)
            return False

        try:
            pygame.init()
        except Exception as exc:
            print(f"Error initialising pygame: {exc}", file=sys.stderr)
            return False

        width = SCREEN_WIDTH * self.scale
        height = SCREEN_HEIGHT * self.scale

        flags = 0
        if self.fullscreen:
            flags |= pygame.FULLSCREEN

        try:
            self.screen = pygame.display.set_mode((width, height), flags)
        except Exception as exc:
            print(f"Error creating display: {exc}", file=sys.stderr)
            pygame.quit()
            return False

        pygame.display.set_caption("Missile Command")
        self.clock = pygame.time.Clock()

        # Load high scores and initialise audio
        self.high_scores = load_scores(self.scores_file)
        self.audio.init()

        # Configure game
        self.game = Game()
        self.game.wave_number = self.start_wave
        self.game.score_display.high_score = get_top_score(self.high_scores)
        if self.tournament:
            self.game.cities.bonus_threshold = 0

        self.running = True
        return True

    # ── Main loop ───────────────────────────────────────────────────────

    def run(self) -> None:
        """Execute the main game loop at 60 FPS."""
        if not self.running:
            return

        try:
            while self.running:
                frame_start = time.perf_counter()

                self._handle_events()
                self._simulate_irqs()
                self._update()
                self._render()

                self.clock.tick(UPDATE_RATE)

                # Performance tracking
                elapsed = time.perf_counter() - frame_start
                self.frame_times.append(elapsed)
                if len(self.frame_times) > 60:
                    self.frame_times.pop(0)
                if self.frame_times:
                    avg = sum(self.frame_times) / len(self.frame_times)
                    self.fps = 1.0 / avg if avg > 0 else 0.0

                # Defer score redraw on heavy frames
                self.defer_score_redraw = elapsed > FRAME_TIME * 1.5
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    # ── Event handling ──────────────────────────────────────────────────

    def _get_target(self) -> tuple[int, int]:
        """Return the current crosshair target in game coordinates."""
        return (self.crosshair_x, self.crosshair_y)

    def _fire_silo(self, silo_index: int) -> None:
        """Attempt to fire from the given silo toward the crosshair."""
        if self.game.state != GameState.RUNNING:
            return
        tx, ty = self._get_target()
        self.game.fire_from_silo(silo_index, tx, ty)

    def _handle_events(self) -> None:
        """Process pygame events.

        Keyboard controls (MAME-style emulation):
            Arrow Keys – move crosshair
            Left Ctrl  – fire from left silo (index 0)
            Left Alt   – fire from center silo (index 1)
            Space      – fire from right silo (index 2)
            1          – start 1-player game
            P          – pause / unpause
            ESC        – exit game

        Mouse controls:
            Mouse movement – move crosshair
            Left button   – fire from left silo (index 0)
            Middle button – fire from center silo (index 1)
            Right button  – fire from right silo (index 2)
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                self.crosshair_x = mx // self.scale
                self.crosshair_y = my // self.scale

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_1:
                    # Start game from attract mode
                    if self.game.state == GameState.ATTRACT:
                        self.game.start_wave()
                elif event.key == pygame.K_LCTRL:
                    self._fire_silo(0)  # left silo
                elif event.key == pygame.K_LALT:
                    self._fire_silo(1)  # center silo
                elif event.key == pygame.K_SPACE:
                    self._fire_silo(2)  # right silo

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:       # left click
                    self._fire_silo(0)      # left silo
                elif event.button == 2:     # middle click
                    self._fire_silo(1)      # center silo
                elif event.button == 3:     # right click
                    self._fire_silo(2)      # right silo

        # Handle held arrow keys for smooth crosshair movement
        if pygame is not None:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LEFT]:
                self.crosshair_x = max(0, self.crosshair_x - self.crosshair_speed)
            if keys[pygame.K_RIGHT]:
                self.crosshair_x = min(SCREEN_WIDTH - 1, self.crosshair_x + self.crosshair_speed)
            if keys[pygame.K_UP]:
                self.crosshair_y = max(0, self.crosshair_y - self.crosshair_speed)
            if keys[pygame.K_DOWN]:
                self.crosshair_y = min(SCREEN_HEIGHT - 1, self.crosshair_y + self.crosshair_speed)

    # ── IRQ simulation ──────────────────────────────────────────────────

    def _simulate_irqs(self) -> None:
        """Simulate the 240 Hz IRQ handler (4× per frame).

        Color cycling happens every 8 IRQs (30 Hz).
        """
        for _ in range(IRQ_PER_FRAME):
            self.irq_counter += 1
            self.color_cycle_counter += 1
            if self.color_cycle_counter >= COLOR_CYCLE_IRQS:
                self.color_cycle_counter = 0

    # ── Game logic update ───────────────────────────────────────────────

    def _update(self) -> None:
        """Run one frame of game logic."""
        prev = self.game.state
        self.game.update()

        # Detect game-over transition and save high score
        if prev != GameState.GAME_OVER and self.game.state == GameState.GAME_OVER:
            self.audio.play(SoundEvent.GAME_OVER)
            score = self.game.score_display.player_score
            score_pos = check_high_score(score, self.high_scores)
            if score_pos > 0:
                name = self._prompt_initials()
                self.high_scores = update_high_scores(score, name, self.high_scores)
                save_high_scores(self.scores_file, self.high_scores)
        elif prev != GameState.WAVE_END and self.game.state == GameState.WAVE_END:
            self.audio.play(SoundEvent.WAVE_END)

    def _prompt_initials(self) -> str:
        """Show a text prompt and let the player type up to 3 initials.

        Returns the entered string, or ``"---"`` if nothing was typed.
        """
        if pygame is None or self.screen is None:
            return "---"

        font_path = "data/fnt/PressStart2P-Regular.ttf"
        try:
            if os.path.isfile(font_path):
                font = pygame.font.Font(font_path, 8 * self.scale)
            else:
                font = pygame.font.Font(None, 16 * self.scale)
        except Exception:
            font = pygame.font.Font(None, 16 * self.scale)

        w = SCREEN_WIDTH * self.scale
        h = SCREEN_HEIGHT * self.scale
        color = (255, 255, 255)
        prompt_text = "ENTER YOUR INITIALS:"
        initials = ""
        finished = False

        while not finished:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    return initials if initials.strip() else "---"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        finished = True
                    elif event.key == pygame.K_BACKSPACE:
                        initials = initials[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        finished = True
                    elif len(initials) < 3 and event.unicode.isalnum():
                        initials += event.unicode

            self.screen.fill((0, 0, 0))
            prompt_surf = font.render(prompt_text, True, color)
            px = w // 2 - prompt_surf.get_width() // 2
            py = h // 2 - prompt_surf.get_height() * 2
            self.screen.blit(prompt_surf, (px, py))

            initials_surf = font.render(initials, True, color)
            ix = w // 2 - initials_surf.get_width() // 2
            iy = py + prompt_surf.get_height() + 8 * self.scale
            self.screen.blit(initials_surf, (ix, iy))

            pygame.display.flip()
            self.clock.tick(UPDATE_RATE)

        return initials if initials.strip() else "---"

    # ── Rendering ───────────────────────────────────────────────────────

    def _render(self) -> None:
        """Execute the rendering pipeline."""
        if self.screen is None:
            return

        self.screen.fill((0, 0, 0))

        # Game-over overlay
        if self.game.state == GameState.GAME_OVER:
            self._render_game_over()

        if self.debug:
            self._render_debug()

        pygame.display.flip()

    def _render_game_over(self) -> None:
        """Draw the GAME OVER screen with final score and high score."""
        if pygame is None or self.screen is None:
            return
        font_path = "data/fnt/PressStart2P-Regular.ttf"
        try:
            if os.path.isfile(font_path):
                font = pygame.font.Font(font_path, 8 * self.scale)
            else:
                font = pygame.font.Font(None, 16 * self.scale)
        except Exception:
            font = pygame.font.Font(None, 16 * self.scale)

        w = SCREEN_WIDTH * self.scale
        h = SCREEN_HEIGHT * self.scale
        color = (255, 255, 255)

        game_over_surf = font.render("THE END", True, color)
        score_surf = font.render(self.game.score_display.format_score(), True, color)
        high_surf = font.render(self.game.score_display.format_high_score(), True, color)

        go_x = w // 2 - game_over_surf.get_width() // 2
        go_y = h // 2 - game_over_surf.get_height() * 2
        self.screen.blit(game_over_surf, (go_x, go_y))

        sc_x = w // 2 - score_surf.get_width() // 2
        sc_y = go_y + game_over_surf.get_height() + 8 * self.scale
        self.screen.blit(score_surf, (sc_x, sc_y))

        hi_x = w // 2 - high_surf.get_width() // 2
        hi_y = sc_y + score_surf.get_height() + 4 * self.scale
        self.screen.blit(high_surf, (hi_x, hi_y))

    def _render_debug(self) -> None:
        """Draw debug overlays (FPS, slot counts)."""
        if pygame is None or self.screen is None:
            return
        font = pygame.font.Font(None, 20)
        from src.config import MAX_ABM_SLOTS, MAX_ICBM_SLOTS, MAX_EXPLOSION_SLOTS
        texts = [
            f"FPS: {self.fps:.1f}",
            f"ABM: {self.game.missiles.active_abm_count}/{MAX_ABM_SLOTS}",
            f"ICBM: {self.game.missiles.active_icbm_count}/{MAX_ICBM_SLOTS}",
            f"Explosions: {self.game.explosions.active_count}/{MAX_EXPLOSION_SLOTS}",
            f"Wave: {self.game.wave_number}",
        ]
        y = 5
        for text in texts:
            surface = font.render(text, True, (0, 255, 0))
            self.screen.blit(surface, (5, y))
            y += 18

    # ── Shutdown ────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Clean up and quit pygame."""
        self.running = False
        self.audio.shutdown()
        if pygame is not None:
            try:
                pygame.quit()
            except Exception:
                pass


# ── Entry point ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Application entry point.  Returns exit code."""
    args = parse_args(argv)

    app = MissileCommandApp(
        scale=args.scale,
        fullscreen=args.fullscreen,
        debug=args.debug,
        start_wave=args.wave,
        tournament=args.tournament,
    )

    if not app.init():
        return 1

    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
