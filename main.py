"""
Main entry point for Missile Command.

Initializes pygame, sets up the 60Hz game loop, and manages the
overall application lifecycle matching the original arcade's timing.

Usage:
    python main.py [OPTIONS]

Options:
    --fullscreen         Launch in fullscreen mode
    --scale N            Display scale multiplier (1-4, default: 3)
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

from src.config import (
    CROSSHAIR_SENSITIVITY,
    DEFAULT_SCALE,
    GROUND_Y,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    UPDATE_RATE,
    WAVE_END_DISPLAY_FRAMES,
)
from src.game import Game, GameState
from src.ui.audio import AudioManager, SoundEvent
from src.ui.high_scores import (
    load_scores, save_high_scores, update_high_scores, get_top_score,
    check_high_score,
)
from src.ui.renderer import Renderer


# ── Constants ───────────────────────────────────────────────────────────────

FRAME_TIME: float = 1.0 / UPDATE_RATE          # ~16.67 ms
IRQ_PER_FRAME: int = 4                          # 240 Hz / 60 Hz
COLOR_CYCLE_IRQS: int = 8                       # 30 Hz color cycling

MIN_SCALE: int = 1
MAX_SCALE: int = 4
TALLY_TICK_INTERVAL_FRAMES: int = 4  # frames between each tally count-up tick

SILO_KEYS: dict[int, int] = {}  # populated lazily once pygame is available


def _silo_key_map() -> dict[int, int]:
    """Map keyboard keys to silo indices (A/S/D or 1/2/3)."""
    if pygame is None:
        return {}
    return {
        pygame.K_a: 0, pygame.K_s: 1, pygame.K_d: 2,
        pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
    }


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
    renderer: Renderer = field(default=None, repr=False)
    clock: object = field(default=None, repr=False)
    game: Game = field(default_factory=Game)
    running: bool = False

    # IRQ simulation
    irq_counter: int = 0
    color_cycle_counter: int = 0

    # Crosshair position (native game coordinates, updated by relative
    # mouse motion -- trackball emulation)
    crosshair_x: float = SCREEN_WIDTH // 2
    crosshair_y: float = SCREEN_HEIGHT // 2

    # Wave-end tally display countdown (frames)
    wave_end_timer: int = 0
    tally_ticks_total: int = 0
    tally_ticks_done: int = 0
    tally_tick_frame_counter: int = 0

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

        try:
            self.renderer = Renderer(scale=self.scale, fullscreen=self.fullscreen)
            self.renderer.create_window()
        except Exception as exc:
            print(f"Error creating display: {exc}", file=sys.stderr)
            pygame.quit()
            return False

        self.clock = pygame.time.Clock()
        pygame.mouse.set_visible(False)

        # Load high scores and initialise audio
        self.high_scores = load_scores(self.scores_file)
        success = self.audio.init()
        if success:
            print("Audio system initialized successfully")
        else:
            print("WARNING: Audio system failed to initialize - game will run silently")

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
        return (int(self.crosshair_x), int(self.crosshair_y))

    def _fire_silo(self, silo_index: int) -> None:
        """Attempt to fire from the given silo toward the crosshair."""
        if self.game.state != GameState.RUNNING:
            return
        tx, ty = self._get_target()
        if not self.game.fire_from_silo(silo_index, tx, ty):
            return
        self.audio.play(SoundEvent.FIRE_ABM)

    def _fire_nearest(self) -> None:
        """Fire from whichever silo has ammo and is nearest the crosshair."""
        if self.game.state != GameState.RUNNING:
            return
        tx, ty = self._get_target()
        if self.game.fire_nearest(tx, ty):
            self.audio.play(SoundEvent.FIRE_ABM)

    def _move_crosshair(self, rel: tuple[int, int]) -> None:
        """Apply relative mouse motion to the crosshair (trackball emulation)."""
        scale = self.renderer.effective_scale if self.renderer else self.scale
        scale = max(scale, 1)
        self.crosshair_x += rel[0] * CROSSHAIR_SENSITIVITY / scale
        self.crosshair_y += rel[1] * CROSSHAIR_SENSITIVITY / scale
        self.crosshair_x = max(0, min(SCREEN_WIDTH - 1, self.crosshair_x))
        self.crosshair_y = max(0, min(GROUND_Y - 1, self.crosshair_y))

    def _handle_events(self) -> None:
        """Process pygame events.

        Keyboard controls:
            A / S / D  or  1 / 2 / 3  -- fire left / center / right silo
            F11        -- toggle fullscreen
            ESC        -- exit game
            1          -- start 1-player game (from attract mode)

        Mouse controls:
            Relative motion -- move crosshair (trackball emulation)
            Left button     -- fire from the nearest silo with ammo
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.MOUSEMOTION:
                self._move_crosshair(event.rel)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_F11:
                    self.renderer.toggle_fullscreen()
                elif event.key == pygame.K_1 and self.game.state == GameState.ATTRACT:
                    self.game.start_wave()
                    self.audio.play(SoundEvent.WAVE_END)
                else:
                    silo = _silo_key_map().get(event.key)
                    if silo is not None:
                        self._fire_silo(silo)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self._fire_nearest()

        # Recenter the OS cursor each frame so relative motion keeps
        # working regardless of screen edges (trackball emulation).
        if self.renderer is not None and self.renderer.window is not None:
            win_w, win_h = self.renderer.window.get_size()
            pygame.mouse.set_pos((win_w // 2, win_h // 2))

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

        if prev != GameState.GAME_OVER and self.game.state == GameState.GAME_OVER:
            self.audio.play(SoundEvent.GAME_OVER)
            score = self.game.score_display.player_score
            score_pos = check_high_score(score, self.high_scores)
            if score_pos > 0:
                name = self._prompt_initials()
                self.high_scores = update_high_scores(score, name, self.high_scores)
                save_high_scores(self.scores_file, self.high_scores)
            self._reset_to_attract()

        elif prev != GameState.WAVE_END and self.game.state == GameState.WAVE_END:
            self.audio.play(SoundEvent.WAVE_END)
            self.wave_end_timer = WAVE_END_DISPLAY_FRAMES
            self.tally_ticks_total = (
                self.game.last_wave_surviving_cities + self.game.last_wave_remaining_abms
            )
            self.tally_ticks_done = 0
            self.tally_tick_frame_counter = 0

        elif self.game.state == GameState.WAVE_END:
            self.wave_end_timer -= 1
            if self.tally_ticks_done < self.tally_ticks_total:
                self.tally_tick_frame_counter += 1
                if self.tally_tick_frame_counter >= TALLY_TICK_INTERVAL_FRAMES:
                    self.tally_tick_frame_counter = 0
                    self.tally_ticks_done += 1
                    self.audio.play(SoundEvent.TALLY_TICK)
            if self.wave_end_timer <= 0:
                self.game.start_wave()

    @property
    def tally_displayed_score(self) -> int:
        """Score shown on the tally screen, counting up tick by tick."""
        base = self.game.score_display.player_score - self.game.last_wave_bonus
        if self.tally_ticks_total <= 0:
            return self.game.score_display.player_score
        fraction = self.tally_ticks_done / self.tally_ticks_total
        return base + round(self.game.last_wave_bonus * fraction)

    def _reset_to_attract(self) -> None:
        """Start a fresh game in attract mode after a game over."""
        high_score = get_top_score(self.high_scores)
        self.game = Game()
        self.game.score_display.high_score = high_score
        if self.tournament:
            self.game.cities.bonus_threshold = 0

    def _prompt_initials(self) -> str:
        """Show a text prompt and let the player type up to 3 initials.

        Returns the entered string, or ``"---"`` if nothing was typed.
        """
        if pygame is None or self.renderer is None or self.renderer.window is None:
            return "---"

        pygame.mouse.set_visible(True)
        font_path = "data/fnt/PressStart2P-Regular.ttf"
        try:
            if os.path.isfile(font_path):
                font = pygame.font.Font(font_path, 8 * self.scale)
            else:
                font = pygame.font.Font(None, 16 * self.scale)
        except Exception:
            font = pygame.font.Font(None, 16 * self.scale)

        window = self.renderer.window
        w, h = window.get_size()
        color = (255, 255, 255)
        prompt_text = "ENTER YOUR INITIALS:"
        initials = ""
        finished = False

        while not finished:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    pygame.mouse.set_visible(False)
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

            window.fill((0, 0, 0))
            prompt_surf = font.render(prompt_text, True, color)
            px = w // 2 - prompt_surf.get_width() // 2
            py = h // 2 - prompt_surf.get_height() * 2
            window.blit(prompt_surf, (px, py))

            initials_surf = font.render(initials, True, color)
            ix = w // 2 - initials_surf.get_width() // 2
            iy = py + prompt_surf.get_height() + 8 * self.scale
            window.blit(initials_surf, (ix, iy))

            pygame.display.flip()
            self.clock.tick(UPDATE_RATE)

        pygame.mouse.set_visible(False)
        return initials if initials.strip() else "---"

    # ── Rendering ───────────────────────────────────────────────────────

    def _render(self) -> None:
        """Execute the rendering pipeline."""
        if self.renderer is None:
            return

        target = self._get_target()
        self.renderer.draw_frame(self.game, target, self.game.frame_count, debug=self.debug)

        if self.game.state == GameState.ATTRACT:
            self._render_attract()
        elif self.game.state == GameState.WAVE_END:
            self._render_wave_end()
        elif self.game.state == GameState.GAME_OVER:
            self._render_game_over()

        self.renderer.present()

    def _center_text(self, text: str, size: int, y: int, color=(255, 255, 255)) -> None:
        from src.ui.renderer import _get_font
        surf = _get_font(size).render(text, True, color)
        x = SCREEN_WIDTH // 2 - surf.get_width() // 2
        self.renderer.native.blit(surf, (x, y))

    def _render_attract(self) -> None:
        self._center_text("MISSILE COMMAND", 10, 70)
        self._center_text("PRESS 1 TO PLAY", 8, 110)
        self._center_text(self.game.score_display.format_high_score(), 8, 140)

    def _render_wave_end(self) -> None:
        mult = self.game.multiplier
        self._center_text(f"WAVE {self.game.wave_number - 1} COMPLETE", 8, 50)
        self._center_text(
            f"CITIES {self.game.last_wave_surviving_cities} X 100 X {mult}", 7, 90,
        )
        self._center_text(
            f"ABMS {self.game.last_wave_remaining_abms} X 5 X {mult}", 7, 105,
        )
        self._center_text(f"BONUS {self.game.last_wave_bonus}", 8, 125)
        self._center_text(f"SCORE {self.tally_displayed_score}", 8, 150)

    def _render_game_over(self) -> None:
        self._center_text("THE END", 10, 90)
        self._center_text(self.game.score_display.format_score(), 8, 120)
        self._center_text(self.game.score_display.format_high_score(), 8, 140)

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
