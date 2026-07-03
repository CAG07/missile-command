"""
Tests for src/ui/audio_cues.py (game-state -> sound-cue mapping) and
src/ui/synth.py (procedural waveform generation).
"""

import numpy as np

from src.game import Game
from src.models.explosion import Explosion
from src.models.missile import Flier, FlierType, SmartBomb
from src.ui import synth
from src.ui.audio import AudioManager, LOOPING_EVENTS, SoundEvent
from src.ui.audio_cues import AudioCueTracker


# ── AudioCueTracker ─────────────────────────────────────────────────────────


class _RecordingAudio(AudioManager):
    """Stand-in AudioManager that records calls instead of touching pygame."""

    def __init__(self):
        super().__init__()
        self.played: list[SoundEvent] = []
        self.loops_started: list[SoundEvent] = []
        self.loops_stopped: list[SoundEvent] = []

    def play(self, event: SoundEvent) -> None:
        self.played.append(event)

    def start_loop(self, event: SoundEvent) -> None:
        self.loops_started.append(event)

    def stop_loop(self, event: SoundEvent) -> None:
        self.loops_stopped.append(event)


class TestAudioCueTracker:
    def test_no_cues_on_first_quiet_frame(self):
        game = Game()
        game.start_wave()
        audio = _RecordingAudio()
        tracker = AudioCueTracker()
        tracker.update(game, audio)
        assert audio.played == []

    def test_new_explosion_triggers_sound(self):
        game = Game()
        game.start_wave()
        audio = _RecordingAudio()
        tracker = AudioCueTracker()
        tracker.update(game, audio)  # baseline: 0 explosions

        game.explosions.add(Explosion(center_x=100, center_y=100))
        tracker.update(game, audio)
        assert SoundEvent.EXPLOSION in audio.played

    def test_silo_low_warns_once_per_wave(self):
        game = Game()
        game.start_wave()
        game.defenses.silos[0].abm_count = 2
        audio = _RecordingAudio()
        tracker = AudioCueTracker()

        tracker.update(game, audio)
        tracker.update(game, audio)
        assert audio.played.count(SoundEvent.SILO_LOW) == 1

    def test_reset_for_new_wave_clears_silo_warnings(self):
        game = Game()
        game.start_wave()
        game.defenses.silos[0].abm_count = 1
        audio = _RecordingAudio()
        tracker = AudioCueTracker()
        tracker.update(game, audio)
        tracker.reset_for_new_wave()
        tracker.update(game, audio)
        assert audio.played.count(SoundEvent.SILO_LOW) == 2

    def test_flier_drone_loop_starts_and_stops(self):
        game = Game()
        game.start_wave()
        audio = _RecordingAudio()
        tracker = AudioCueTracker()

        flier = Flier(
            flier_type=FlierType.BOMBER, altitude=115, direction=1,
            speed=1, resurrection_timer=60, firing_timer=30,
        )
        game.missiles.flier_slot = flier
        tracker.update(game, audio)
        assert SoundEvent.FLIER_DRONE in audio.loops_started

        flier.deactivate()
        tracker.update(game, audio)
        assert SoundEvent.FLIER_DRONE in audio.loops_stopped

    def test_smart_bomb_warble_loop_starts(self):
        game = Game()
        game.start_wave()
        audio = _RecordingAudio()
        tracker = AudioCueTracker()

        sb = SmartBomb(entry_x=100, entry_y=100, target_x=100, target_y=220, speed=1)
        game.missiles.icbm_slots[0] = sb
        tracker.update(game, audio)
        assert SoundEvent.SMART_BOMB_WARBLE in audio.loops_started

    def test_stop_all_loops(self):
        audio = _RecordingAudio()
        tracker = AudioCueTracker()
        tracker._prev_flier_active = True
        tracker._prev_smart_bomb_active = True
        tracker.stop_all_loops(audio)
        assert SoundEvent.FLIER_DRONE in audio.loops_stopped
        assert SoundEvent.SMART_BOMB_WARBLE in audio.loops_stopped
        assert tracker._prev_flier_active is False
        assert tracker._prev_smart_bomb_active is False


class TestLoopingEvents:
    def test_looping_events_contains_flier_and_smart_bomb(self):
        assert SoundEvent.FLIER_DRONE in LOOPING_EVENTS
        assert SoundEvent.SMART_BOMB_WARBLE in LOOPING_EVENTS
        assert SoundEvent.FIRE_ABM not in LOOPING_EVENTS


# ── Synth waveform generation ────────────────────────────────────────────────


class TestSynthPrimitives:
    def test_sine_range(self):
        wf = synth.sine(440, 0.1)
        assert wf.min() >= -1.0001 and wf.max() <= 1.0001
        assert len(wf) == int(synth.SAMPLE_RATE * 0.1)

    def test_square_is_bipolar(self):
        wf = synth.square(440, 0.05)
        assert set(np.unique(wf)).issubset({-1.0, 1.0})

    def test_noise_bounded(self):
        wf = synth.noise(0.05)
        assert wf.min() >= -1.0 and wf.max() <= 1.0

    def test_envelope_fades_edges_to_zero(self):
        env = synth.envelope(1000, attack=0.1, release=0.1)
        assert env[0] == 0.0
        assert env[-1] < 0.01

    def test_to_int16_stereo_shape_and_dtype(self):
        wf = synth.sine(440, 0.05)
        arr = synth.to_int16_stereo(wf, volume=0.5)
        assert arr.dtype == np.int16
        assert arr.shape == (len(wf), 2)
        assert np.array_equal(arr[:, 0], arr[:, 1])


class TestSynthRecipes:
    """Every recipe should produce a valid, clipped int16 stereo array."""

    RECIPES = [
        synth.fire_abm, synth.explosion, synth.silo_low, synth.cant_fire,
        synth.wave_start, synth.wave_end_bonus, synth.tally_tick,
        synth.bonus_city, synth.game_over, synth.flier_drone_loop,
        synth.smart_bomb_warble_loop,
    ]

    def test_all_recipes_produce_valid_arrays(self):
        for recipe in self.RECIPES:
            arr = recipe()
            assert arr.dtype == np.int16
            assert arr.ndim == 2 and arr.shape[1] == 2
            assert arr.shape[0] > 0
