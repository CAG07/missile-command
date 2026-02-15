"""
Main entry point for Missile Command.

Initializes pygame, sets up the 60Hz game loop, and manages the
overall application lifecycle matching the original arcade's timing.

Usage:
    python main.py [OPTIONS]

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
import sys
import time
from dataclasses import dataclass, field

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from src.config import SCREEN_WIDTH, SCREEN_HEIGHT, UPDATE_RATE
from src.game import Game, GameState


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

    # Performance tracking
    frame_times: list[float] = field(default_factory=list)
    fps: float = 0.0
    defer_score_redraw: bool = False

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

        # Configure game
        self.game = Game()
        self.game.wave_number = self.start_wave
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

    def _handle_events(self) -> None:
        """Process pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False

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
        self.game.update()

    # ── Rendering ───────────────────────────────────────────────────────

    def _render(self) -> None:
        """Execute the rendering pipeline."""
        if self.screen is None:
            return

        self.screen.fill((0, 0, 0))

        if self.debug:
            self._render_debug()

        pygame.display.flip()

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
