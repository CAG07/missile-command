"""
Entry point for Missile Command.

All application logic (pygame setup, the 60Hz loop, input, audio
cues, rendering orchestration) lives in ``src/app.py``. This module
just parses CLI arguments and launches it.

Usage:
    python main.py [OPTIONS]

Options:
    --fullscreen         Launch in fullscreen mode
    --scale N            Display scale multiplier (1-4, default: 3)
    --debug              Enable debug overlays
    --attract            Start in attract mode
    --wave N             Start at specific wave (testing)
    --mute               Disable all audio
    --cities N           Starting city count (4-7, default: 6)
    --bonus-interval N   Bonus city point interval (0=off, 8000-14000, default: 10000)
    --marathon           Marathon mode (default)
    --tournament         Tournament mode (no bonus cities)

References:
    - Missile Command Disassembly.pdf
    - https://6502disassembly.com/va-missile-command/
"""

from __future__ import annotations

import sys

from src.app import MissileCommandApp, parse_args


def main(argv: list[str] | None = None) -> int:
    """Application entry point.  Returns exit code."""
    args = parse_args(argv)

    app = MissileCommandApp(
        scale=args.scale,
        fullscreen=args.fullscreen,
        debug=args.debug,
        start_wave=args.wave,
        tournament=args.tournament,
        mute=args.mute,
        starting_cities=args.cities,
        bonus_interval=args.bonus_interval,
    )

    if not app.init():
        return 1

    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
