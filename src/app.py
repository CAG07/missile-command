"""
Application controller for Missile Command.

Owns the pygame display, the 60Hz main loop, input handling, audio
cue triggering, and screen rendering orchestration. ``main.py`` is
just a thin CLI entry point around :class:`MissileCommandApp`.

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

from src.config import (
    BONUS_CITY_POINTS,
    CROSSHAIR_SENSITIVITY,
    DEFAULT_SCALE,
    GAME_OVER_DISPLAY_FRAMES,
    GROUND_Y,
    NUM_CITIES_DEFAULT,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    UPDATE_RATE,
    WAVE_END_DISPLAY_FRAMES,
    WAVE_INTRO_DISPLAY_FRAMES,
)
from src.attract import AttractDemo
from src.game import Game, GameState
from src.models.city import CityManager
from src.ui.audio import AudioManager, SoundEvent
from src.ui.audio_cues import AudioCueTracker
from src.ui.high_scores import (
    load_scores, save_high_scores, update_high_scores, get_top_score,
    check_high_score,
)
from src.ui.renderer import Renderer, get_font


# ── Constants ───────────────────────────────────────────────────────────────

FRAME_TIME: float = 1.0 / UPDATE_RATE          # ~16.67 ms
IRQ_PER_FRAME: int = 4                          # 240 Hz / 60 Hz
COLOR_CYCLE_IRQS: int = 8                       # 30 Hz color cycling

MIN_SCALE: int = 1
MAX_SCALE: int = 4
TALLY_TICK_INTERVAL_FRAMES: int = 4  # frames between each tally count-up tick


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
    parser.add_argument(
        "--mute", action="store_true",
        help="Disable all audio",
    )
    parser.add_argument(
        "--cities", type=int, default=NUM_CITIES_DEFAULT,
        choices=range(4, 8), metavar="N",
        help="Starting city count (4-7, default: 6)",
    )
    parser.add_argument(
        "--bonus-interval", type=int, default=BONUS_CITY_POINTS,
        choices=[0, 8000, 10000, 12000, 14000], metavar="N",
        help="Bonus city point interval (0=off, 8000-14000, default: 10000)",
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
    mute: bool = False
    starting_cities: int = NUM_CITIES_DEFAULT
    bonus_interval: int = BONUS_CITY_POINTS

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

    # Wave-intro screen ("WAVE N" + alarm before attacks begin)
    _pending_wave_intro: bool = field(default=False, repr=False)
    wave_intro_timer: int = 0

    # Mouse-driven high-score initials entry (see _update_initials_entry)
    _awaiting_initials: bool = field(default=False, repr=False)
    _initials: list = field(default_factory=lambda: ["A", "A", "A"], repr=False)
    _initials_slot: int = field(default=0, repr=False)
    _initials_pending_score: int = field(default=0, repr=False)

    # Performance tracking
    frame_times: list[float] = field(default_factory=list)
    fps: float = 0.0
    defer_score_redraw: bool = False

    # Audio
    audio: AudioManager = field(default_factory=AudioManager)
    audio_cues: AudioCueTracker = field(default_factory=AudioCueTracker)

    # Game-over "THE END" animation timer (frames)
    game_over_timer: int = 0
    _game_over_initials_done: bool = field(default=False, repr=False)

    # High scores
    high_scores: dict = field(default_factory=dict)
    scores_file: str = "scores.json"
    _prev_state: GameState = GameState.ATTRACT

    # Attract-mode autoplay demo (hidden Game the computer plays)
    attract_demo: AttractDemo = field(default_factory=AttractDemo)

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
        if self.mute:
            self.audio.enabled = False
        success = self.audio.init()
        if success:
            print("Audio system initialized successfully")
        elif self.mute:
            print("Audio muted via --mute")
        else:
            print("WARNING: Audio system failed to initialize - game will run silently")

        # Configure game
        self.game = Game()
        self.game.wave_number = self.start_wave
        self.game.score_display.high_score = get_top_score(self.high_scores)
        self.game.cities = CityManager(
            num_cities=self.starting_cities, bonus_threshold=self.bonus_interval,
        )
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
            self.audio.play(SoundEvent.CANT_FIRE)
            return
        self.audio.play(SoundEvent.FIRE_ABM)

    def _fire_nearest(self) -> None:
        """Fire from whichever silo has ammo and is nearest the crosshair."""
        if self.game.state != GameState.RUNNING:
            return
        tx, ty = self._get_target()
        if self.game.fire_nearest(tx, ty):
            self.audio.play(SoundEvent.FIRE_ABM)
        else:
            self.audio.play(SoundEvent.CANT_FIRE)

    def _start_game_from_attract(self) -> None:
        """Leave attract mode and show the wave intro before real play begins."""
        self._begin_wave_intro()

    def _begin_wave_intro(self) -> None:
        """Show the "WAVE N" intro screen (alarm + warning) before the
        next wave's attacks begin. Purely an app-level display phase --
        the underlying Game doesn't gain a new state for this since
        Game.update() already no-ops for any state other than RUNNING."""
        self._pending_wave_intro = True
        self.wave_intro_timer = WAVE_INTRO_DISPLAY_FRAMES
        self.audio.play(SoundEvent.WAVE_START)

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
                    self._start_game_from_attract()
                else:
                    silo = _silo_key_map().get(event.key)
                    if silo is not None:
                        self._fire_silo(silo)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self._awaiting_initials:
                        self._initials_slot += 1
                    else:
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
        if self._awaiting_initials:
            self._update_initials_entry()
            return

        if self._pending_wave_intro:
            self.wave_intro_timer -= 1
            if self.wave_intro_timer <= 0:
                self._pending_wave_intro = False
                self.game.start_wave()
            return

        if self.game.state == GameState.ATTRACT:
            self.attract_demo.update()
            return

        prev = self.game.state
        self.game.update()

        if prev != GameState.GAME_OVER and self.game.state == GameState.GAME_OVER:
            self.audio_cues.stop_all_loops(self.audio)
            self.audio.play(SoundEvent.GAME_OVER)
            self.game_over_timer = 0
            self._game_over_initials_done = False
            return

        if self.game.state == GameState.GAME_OVER:
            self.game_over_timer += 1
            if (
                self.game_over_timer >= GAME_OVER_DISPLAY_FRAMES
                and not self._game_over_initials_done
            ):
                self._game_over_initials_done = True
                score = self.game.score_display.player_score
                score_pos = check_high_score(score, self.high_scores)
                if score_pos > 0:
                    self._initials = ["A", "A", "A"]
                    self._initials_slot = 0
                    self._initials_pending_score = score
                    self._awaiting_initials = True
                else:
                    self._reset_to_attract()
            return

        if prev != GameState.WAVE_END and self.game.state == GameState.WAVE_END:
            self.audio_cues.stop_all_loops(self.audio)
            self.audio.play(SoundEvent.WAVE_END)
            self.wave_end_timer = WAVE_END_DISPLAY_FRAMES
            self.tally_ticks_total = (
                self.game.last_wave_surviving_cities + self.game.last_wave_remaining_abms
            )
            self.tally_ticks_done = 0
            self.tally_tick_frame_counter = 0
            return

        if self.game.state == GameState.WAVE_END:
            self.wave_end_timer -= 1
            if self.tally_ticks_done < self.tally_ticks_total:
                self.tally_tick_frame_counter += 1
                if self.tally_tick_frame_counter >= TALLY_TICK_INTERVAL_FRAMES:
                    self.tally_tick_frame_counter = 0
                    self.tally_ticks_done += 1
                    self.audio.play(SoundEvent.TALLY_TICK)
            if self.wave_end_timer <= 0:
                self.audio_cues.reset_for_new_wave()
                self._begin_wave_intro()
            return

        if self.game.state == GameState.RUNNING:
            self.audio_cues.update(self.game, self.audio)

    def _update_initials_entry(self) -> None:
        """Advance the mouse-driven initials entry by one frame.

        The currently-scrubbed letter is recomputed every frame from
        ``crosshair_x``; a left click (handled in ``_handle_events``)
        advances ``_initials_slot``. Once all 3 slots are confirmed,
        save the score and return to attract mode.
        """
        charset = self.INITIALS_CHARSET
        fraction = self.crosshair_x / SCREEN_WIDTH
        idx = max(0, min(len(charset) - 1, int(fraction * len(charset))))
        if self._initials_slot < 3:
            self._initials[self._initials_slot] = charset[idx]
            return

        name = "".join(self._initials)
        self.high_scores = update_high_scores(
            self._initials_pending_score, name, self.high_scores,
        )
        save_high_scores(self.scores_file, self.high_scores)
        self._awaiting_initials = False
        self._reset_to_attract()

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
        self.game.cities = CityManager(
            num_cities=self.starting_cities, bonus_threshold=self.bonus_interval,
        )
        if self.tournament:
            self.game.cities.bonus_threshold = 0
        self.attract_demo.restart()

    #: Selectable characters for trackball-style initials entry.
    INITIALS_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "

    def _render_initials_entry(
        self, initials: list[str], active_slot: int, current_char: str
    ) -> None:
        """Draw the trackball-style initials entry screen."""
        self.renderer.native.fill((0, 0, 0))
        self._center_text("ENTER YOUR INITIALS", 8, 50)
        self._center_text("MOVE MOUSE, CLICK TO SELECT", 6, 68)
        self._center_text(self.game.score_display.format_score(), 8, 150)

        slot_w = 24
        start_x = SCREEN_WIDTH // 2 - (slot_w * 3) // 2
        for i in range(3):
            if i < active_slot:
                ch, color = initials[i], (255, 255, 255)
            elif i == active_slot:
                ch, color = current_char, (255, 220, 0)
            else:
                ch, color = "_", (120, 120, 120)
            surf = get_font(14).render(ch, True, color)
            self.renderer.native.blit(surf, (start_x + i * slot_w, 100))

    # ── Rendering ───────────────────────────────────────────────────────

    def _render(self) -> None:
        """Execute the rendering pipeline."""
        if self.renderer is None:
            return

        if self._awaiting_initials:
            fraction = self.crosshair_x / SCREEN_WIDTH
            idx = max(0, min(len(self.INITIALS_CHARSET) - 1, int(fraction * len(self.INITIALS_CHARSET))))
            self._render_initials_entry(self._initials, self._initials_slot, self.INITIALS_CHARSET[idx])
        elif self._pending_wave_intro:
            self._render_wave_intro_screen()
        elif self.game.state == GameState.ATTRACT:
            # Show the autoplay demo running behind the attract overlay,
            # matching the arcade's live (not pre-recorded) demo mode.
            demo_game = self.attract_demo.game
            self.renderer.draw_frame(
                demo_game, self.attract_demo.crosshair_pos, demo_game.frame_count, debug=self.debug,
            )
            self._render_attract()
        else:
            target = self._get_target()
            self.renderer.draw_frame(self.game, target, self.game.frame_count, debug=self.debug)
            if self.game.state == GameState.WAVE_END:
                self._render_wave_end()
            elif self.game.state == GameState.GAME_OVER:
                self._render_game_over()

        self.renderer.present()

    def _render_wave_intro_screen(self) -> None:
        """Draw the "WAVE N" intro screen over the current landscape."""
        target = self._get_target()
        self.renderer.draw_frame(self.game, target, self.game.frame_count, debug=self.debug)
        self._center_text(f"WAVE {self.game.wave_number}", 10, 90)
        self._center_text("GET READY", 7, 110)

    def _center_text(self, text: str, size: int, y: int, color=(255, 255, 255)) -> None:
        surf = get_font(size).render(text, True, color)
        x = SCREEN_WIDTH // 2 - surf.get_width() // 2
        self.renderer.native.blit(surf, (x, y))

    def _render_attract(self) -> None:
        self._center_text("MISSILE COMMAND", 10, 20)
        self._center_text("PRESS 1 TO PLAY", 7, 40)
        self._render_high_score_table()

    def _render_high_score_table(self) -> None:
        """Draw the top-10 leaderboard, centered in the space between the
        title/subtitle and the ground line."""
        self._center_text("HIGH SCORES", 8, 78)
        y = 93
        for pos in [str(i) for i in range(1, 11)]:
            record = self.high_scores.get(pos)
            if not record:
                continue
            name = str(record.get("name", "---"))[:3].ljust(3)
            score = int(record.get("score", 0) or 0)
            line = f"{pos.rjust(2)}. {name}  {score:06d}"
            self._center_text(line, 6, y)
            y += 8

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
        self.renderer.draw_the_end(self.game_over_timer)
        self._center_text(self.game.score_display.format_score(), 8, 190)
        self._center_text(self.game.score_display.format_high_score(), 8, 205)

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
