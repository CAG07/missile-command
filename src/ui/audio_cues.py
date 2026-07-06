"""
Frame-to-frame game-state -> sound-cue mapping.

Watches :class:`~src.game.Game` state each frame and decides which
one-shot sounds to fire and which continuous loops (flier drone,
smart bomb warble) should be playing, keeping that mapping out of the
application/input loop in ``src/app.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config import SILO_LOW_THRESHOLD
from src.game import Game
from src.ui.audio import AudioManager, SoundEvent

_LOOP_EVENTS = (SoundEvent.FLIER_DRONE, SoundEvent.SMART_BOMB_WARBLE)


@dataclass
class AudioCueTracker:
    """Tracks prior-frame state to detect newly-occurring game events."""

    _prev_explosion_count: int = field(default=0, repr=False)
    _prev_flier_active: bool = field(default=False, repr=False)
    _prev_smart_bomb_active: bool = field(default=False, repr=False)
    _silo_low_warned: set = field(default_factory=set, repr=False)

    def reset_for_new_wave(self) -> None:
        """Clear per-wave warning state (ammo resets each wave)."""
        self._silo_low_warned.clear()
        self._prev_explosion_count = 0

    def stop_all_loops(self, audio: AudioManager) -> None:
        """Silence any continuous loop (e.g. on game over / wave end)."""
        for event in _LOOP_EVENTS:
            audio.stop_loop(event)
        self._prev_flier_active = False
        self._prev_smart_bomb_active = False

    def update(self, game: Game, audio: AudioManager) -> None:
        """Compare this frame's state to the last and trigger sound cues."""
        explosion_count = game.explosions.active_count
        if explosion_count > self._prev_explosion_count:
            audio.play(SoundEvent.EXPLOSION)
        self._prev_explosion_count = explosion_count

        for silo in game.defenses.silos:
            if (
                not silo.is_destroyed
                and 0 < silo.abm_count <= SILO_LOW_THRESHOLD
                and silo.silo_index not in self._silo_low_warned
            ):
                audio.play(SoundEvent.SILO_LOW)
                self._silo_low_warned.add(silo.silo_index)

        flier = game.missiles.flier_slot
        flier_active = flier is not None and flier.is_active
        if flier_active and not self._prev_flier_active:
            audio.start_loop(SoundEvent.FLIER_DRONE)
        elif not flier_active and self._prev_flier_active:
            audio.stop_loop(SoundEvent.FLIER_DRONE)
        self._prev_flier_active = flier_active

        smart_bomb_active = game.missiles.smart_bomb_count > 0
        if smart_bomb_active and not self._prev_smart_bomb_active:
            audio.start_loop(SoundEvent.SMART_BOMB_WARBLE)
        elif not smart_bomb_active and self._prev_smart_bomb_active:
            audio.stop_loop(SoundEvent.SMART_BOMB_WARBLE)
        self._prev_smart_bomb_active = smart_bomb_active
