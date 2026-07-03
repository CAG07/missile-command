"""
Audio manager for Missile Command.

Loads sound effects from disk if present, and otherwise synthesizes
them procedurally with numpy (src.ui.synth), matching the original
arcade's POKEY-chip sound design without shipping ROM samples. Falls
back to silent operation when pygame.mixer or numpy is unavailable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional


class SoundEvent(Enum):
    """Identifiers for game sound effects (see disassembly $78f1)."""
    FIRE_ABM = auto()
    EXPLOSION = auto()
    SILO_LOW = auto()
    CANT_FIRE = auto()
    WAVE_START = auto()
    WAVE_END = auto()
    BONUS_CITY = auto()
    TALLY_TICK = auto()
    GAME_OVER = auto()
    FLIER_DRONE = auto()
    SMART_BOMB_WARBLE = auto()


# Continuous effects that loop until explicitly stopped.
LOOPING_EVENTS: frozenset[SoundEvent] = frozenset({
    SoundEvent.FLIER_DRONE,
    SoundEvent.SMART_BOMB_WARBLE,
})

# Map each event to its .wav file name inside data/sfx/, if a real
# sample is provided in preference to procedural synthesis.
_SOUND_FILES: dict[SoundEvent, str] = {
    SoundEvent.FIRE_ABM: "abm_launch.wav",
    SoundEvent.EXPLOSION: "explosion.wav",
    SoundEvent.SILO_LOW: "silo_low.wav",
    SoundEvent.CANT_FIRE: "cant_fire.wav",
    SoundEvent.WAVE_START: "start_wave.wav",
    SoundEvent.WAVE_END: "bonus_points.wav",
    SoundEvent.BONUS_CITY: "bonus_city.wav",
    SoundEvent.TALLY_TICK: "tally_tick.wav",
    SoundEvent.GAME_OVER: "game_over.wav",
    SoundEvent.FLIER_DRONE: "flier.wav",
    SoundEvent.SMART_BOMB_WARBLE: "smart_bomb.wav",
}


@dataclass
class AudioManager:
    """Loads/synthesizes and plays sound effects.

    Falls back to silent operation when the mixer is unavailable or
    numpy cannot be imported for synthesis.
    """

    sfx_dir: str = os.path.join("data", "sfx")
    enabled: bool = True

    # Internal state
    _initialized: bool = field(default=False, repr=False)
    _sounds: dict[SoundEvent, Any] = field(default_factory=dict, repr=False)
    _loop_channels: dict[SoundEvent, Any] = field(default_factory=dict, repr=False)

    def init(self) -> bool:
        """Initialise the mixer and load/synthesize all sound effects.

        Returns True if the mixer was initialised successfully.

        When running inside a Python virtual-environment the default SDL
        audio driver may not be detected.  We try several common drivers
        before giving up.
        """
        if not self.enabled:
            print("AudioManager: disabled via config")
            return False

        try:
            import pygame.mixer

            # Check if already initialized
            if pygame.mixer.get_init():
                print(f"AudioManager: mixer already initialized: {pygame.mixer.get_init()}")
                self._initialized = True
            else:
                drivers = [None, "pulseaudio", "alsa", "dsp", "dummy"]
                initialized = False
                original_driver = os.environ.get("SDL_AUDIODRIVER")

                for driver in drivers:
                    try:
                        if driver is not None:
                            os.environ["SDL_AUDIODRIVER"] = driver
                            print(f"AudioManager: trying driver '{driver}'")
                        else:
                            print("AudioManager: trying default driver")

                        # Use specific mixer parameters for consistent
                        # audio quality across platforms.
                        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                        print(f"AudioManager: SUCCESS with driver '{driver or 'default'}'")
                        print(f"AudioManager: mixer config: {pygame.mixer.get_init()}")
                        initialized = True
                        break
                    except Exception as e:
                        print(f"AudioManager: FAILED with driver '{driver or 'default'}': {e}")
                        continue

                if not initialized:
                    if original_driver is not None:
                        os.environ["SDL_AUDIODRIVER"] = original_driver
                    elif "SDL_AUDIODRIVER" in os.environ:
                        del os.environ["SDL_AUDIODRIVER"]
                    print("AudioManager: all drivers failed")
                    self._initialized = False
                    return False

                self._initialized = True

        except ImportError as e:
            print(f"AudioManager: pygame.mixer import failed: {e}")
            self._initialized = False
            return False
        except Exception as e:
            print(f"AudioManager: unexpected error: {e}")
            self._initialized = False
            return False

        self._load_sounds()
        self._synthesize_missing_sounds()
        return True

    def _load_sounds(self) -> None:
        """Attempt to load each configured sound file from disk."""
        if not self._initialized:
            print("AudioManager: cannot load sounds, not initialized")
            return

        try:
            import pygame.mixer
        except ImportError:
            print("AudioManager: pygame.mixer not available for loading")
            return

        print(f"AudioManager: loading sounds from '{self.sfx_dir}'")
        for event, filename in _SOUND_FILES.items():
            path = os.path.join(self.sfx_dir, filename)
            if os.path.isfile(path):
                try:
                    self._sounds[event] = pygame.mixer.Sound(path)
                    print(f"AudioManager: loaded {event.name} from {filename}")
                except Exception as e:
                    print(f"AudioManager: FAILED to load {filename}: {e}")
            else:
                print(f"AudioManager: file not found: {path}")

        print(f"AudioManager: loaded {len(self._sounds)}/{len(_SOUND_FILES)} sounds")

    def _synthesize_missing_sounds(self) -> None:
        """Procedurally generate any sound not already loaded from disk."""
        if not self._initialized:
            return
        try:
            import pygame.sndarray
            from src.ui import synth
        except ImportError as e:
            print(f"AudioManager: synthesis unavailable ({e}), running silent for missing sounds")
            return

        recipes = {
            SoundEvent.FIRE_ABM: synth.fire_abm,
            SoundEvent.EXPLOSION: synth.explosion,
            SoundEvent.SILO_LOW: synth.silo_low,
            SoundEvent.CANT_FIRE: synth.cant_fire,
            SoundEvent.WAVE_START: synth.wave_start,
            SoundEvent.WAVE_END: synth.wave_end_bonus,
            SoundEvent.BONUS_CITY: synth.bonus_city,
            SoundEvent.TALLY_TICK: synth.tally_tick,
            SoundEvent.GAME_OVER: synth.game_over,
            SoundEvent.FLIER_DRONE: synth.flier_drone_loop,
            SoundEvent.SMART_BOMB_WARBLE: synth.smart_bomb_warble_loop,
        }
        synthesized = 0
        for event, recipe in recipes.items():
            if event in self._sounds:
                continue
            try:
                array = recipe()
                self._sounds[event] = pygame.sndarray.make_sound(array)
                synthesized += 1
            except Exception as e:
                print(f"AudioManager: FAILED to synthesize {event.name}: {e}")
        print(f"AudioManager: synthesized {synthesized} sound(s)")

    def play(self, event: SoundEvent) -> None:
        """Play the (non-looping) sound associated with *event*, if available."""
        if not self._initialized or not self.enabled:
            return
        sound = self._sounds.get(event)
        if sound is not None:
            try:
                sound.play()
            except Exception:
                pass

    def start_loop(self, event: SoundEvent) -> None:
        """Start looping *event* if it isn't already playing."""
        if not self._initialized or not self.enabled:
            return
        if self._loop_channels.get(event) is not None:
            return
        sound = self._sounds.get(event)
        if sound is None:
            return
        try:
            self._loop_channels[event] = sound.play(loops=-1)
        except Exception:
            pass

    def stop_loop(self, event: SoundEvent) -> None:
        """Stop a looping sound started with :meth:`start_loop`."""
        channel = self._loop_channels.get(event)
        if channel is not None:
            try:
                channel.stop()
            except Exception:
                pass
            self._loop_channels[event] = None

    def shutdown(self) -> None:
        """Release mixer resources."""
        if self._initialized:
            for event in list(self._loop_channels):
                self.stop_loop(event)
            try:
                import pygame.mixer
                pygame.mixer.quit()
            except Exception:
                pass
            self._initialized = False
            self._sounds.clear()
