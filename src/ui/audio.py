"""
Audio manager for Missile Command.

Provides sound-effect loading and playback, gracefully degrading when
pygame.mixer is unavailable or sound files are missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class SoundEvent(Enum):
    """Identifiers for game sound effects."""
    FIRE_ABM = auto()
    EXPLOSION = auto()
    ICBM_LAUNCH = auto()
    CITY_DESTROYED = auto()
    GAME_OVER = auto()
    WAVE_END = auto()
    BONUS_CITY = auto()


# Map each event to its .wav file name inside data/sfx/
_SOUND_FILES: dict[SoundEvent, str] = {
    SoundEvent.FIRE_ABM: "fire_abm.wav",
    SoundEvent.EXPLOSION: "explosion.wav",
    SoundEvent.ICBM_LAUNCH: "icbm_launch.wav",
    SoundEvent.CITY_DESTROYED: "city_destroyed.wav",
    SoundEvent.GAME_OVER: "game_over.wav",
    SoundEvent.WAVE_END: "wave_end.wav",
    SoundEvent.BONUS_CITY: "bonus_city.wav",
}


@dataclass
class AudioManager:
    """Loads and plays sound effects.

    Falls back to silent operation when mixer is unavailable or
    individual sound files are missing.
    """

    sfx_dir: str = os.path.join("data", "sfx")
    enabled: bool = True

    # Internal state
    _initialized: bool = field(default=False, repr=False)
    _sounds: dict[SoundEvent, Any] = field(default_factory=dict, repr=False)

    def init(self) -> bool:
        """Initialise the mixer and load available sound files.

        Returns True if the mixer was initialised successfully.

        When running inside a Python virtual-environment the default SDL
        audio driver may not be detected.  We try several common drivers
        before giving up.
        """
        if not self.enabled:
            return False

        try:
            import pygame.mixer
            if not pygame.mixer.get_init():
                # Try default driver first; if that fails, try common
                # fallback drivers that work inside virtual environments.
                drivers = [None, "pulseaudio", "alsa", "dsp", "dummy"]
                initialized = False
                original_driver = os.environ.get("SDL_AUDIODRIVER")
                for driver in drivers:
                    try:
                        if driver is not None:
                            os.environ["SDL_AUDIODRIVER"] = driver
                        pygame.mixer.init()
                        initialized = True
                        break
                    except Exception:
                        continue
                # Restore original environment variable only when
                # initialisation failed so that a working fallback
                # driver stays active for any future re-init.
                if not initialized:
                    if original_driver is not None:
                        os.environ["SDL_AUDIODRIVER"] = original_driver
                    elif "SDL_AUDIODRIVER" in os.environ:
                        del os.environ["SDL_AUDIODRIVER"]
                if not initialized:
                    self._initialized = False
                    return False
            self._initialized = True
        except Exception:
            self._initialized = False
            return False

        self._load_sounds()
        return True

    def _load_sounds(self) -> None:
        """Attempt to load each configured sound file."""
        if not self._initialized:
            return
        try:
            import pygame.mixer
        except ImportError:
            return

        for event, filename in _SOUND_FILES.items():
            path = os.path.join(self.sfx_dir, filename)
            if os.path.isfile(path):
                try:
                    self._sounds[event] = pygame.mixer.Sound(path)
                except Exception:
                    pass

    def play(self, event: SoundEvent) -> None:
        """Play the sound associated with *event*, if available."""
        if not self._initialized or not self.enabled:
            return
        sound = self._sounds.get(event)
        if sound is not None:
            try:
                sound.play()
            except Exception:
                pass

    def shutdown(self) -> None:
        """Release mixer resources."""
        if self._initialized:
            try:
                import pygame.mixer
                pygame.mixer.quit()
            except Exception:
                pass
            self._initialized = False
            self._sounds.clear()
