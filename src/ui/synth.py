"""
Procedural POKEY-style sound synthesis for Missile Command.

Generates all sound effects with numpy at load time instead of
shipping ROM samples. Waveform generators are simple (square, sine,
noise, frequency sweeps) to match the coarse, four-channel character
of the original arcade's POKEY chip.

References:
    - Missile Command Disassembly.pdf (Sound section, $78f1 channel table)
"""

from __future__ import annotations

import random

import numpy as np

SAMPLE_RATE = 44100


# ── Waveform primitives ─────────────────────────────────────────────────────


def envelope(n: int, attack: float = 0.05, release: float = 0.3) -> np.ndarray:
    """Return a length-*n* linear attack/release amplitude envelope."""
    env = np.ones(n, dtype=np.float64)
    a = int(n * attack)
    r = int(n * release)
    if a > 0:
        env[:a] *= np.linspace(0.0, 1.0, a)
    if r > 0:
        env[n - r:] *= np.linspace(1.0, 0.0, r)
    return env


def sine(freq: float, duration: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    t = np.linspace(0.0, duration, int(sample_rate * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t)


def square(freq: float, duration: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    return np.where(sine(freq, duration, sample_rate) >= 0, 1.0, -1.0)


def noise(duration: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n = int(sample_rate * duration)
    return np.random.default_rng().uniform(-1.0, 1.0, n)


def sweep(
    f_start: float, f_end: float, duration: float,
    sample_rate: int = SAMPLE_RATE, squarewave: bool = False,
) -> np.ndarray:
    """A frequency sweep from *f_start* to *f_end* over *duration* seconds."""
    n = int(sample_rate * duration)
    freq_t = np.linspace(f_start, f_end, n)
    phase = 2 * np.pi * np.cumsum(freq_t) / sample_rate
    wf = np.sin(phase)
    return np.sign(wf) if squarewave else wf


def to_int16_stereo(waveform: np.ndarray, volume: float = 0.5) -> np.ndarray:
    """Clamp/scale a float waveform to int16 stereo samples for sndarray."""
    clipped = np.clip(waveform, -1.0, 1.0) * volume
    mono = (clipped * 32767).astype(np.int16)
    return np.ascontiguousarray(np.column_stack([mono, mono]))


# ── Per-event recipes ───────────────────────────────────────────────────────
# Each returns an int16 stereo numpy array ready for pygame.sndarray.make_sound.


def fire_abm() -> np.ndarray:
    dur = 0.12
    wf = sweep(900, 300, dur, squarewave=True) * envelope(int(SAMPLE_RATE * dur), 0.02, 0.4)
    return to_int16_stereo(wf, volume=0.35)


def explosion() -> np.ndarray:
    dur = 0.5
    n = int(SAMPLE_RATE * dur)
    wf = noise(dur) * 0.7 + sine(75, dur) * 0.4
    wf *= envelope(n, 0.01, 0.85)
    return to_int16_stereo(wf, volume=0.5)


def silo_low() -> np.ndarray:
    dur = 0.2
    wf = square(880, dur) * envelope(int(SAMPLE_RATE * dur), 0.05, 0.5)
    return to_int16_stereo(wf, volume=0.3)


def cant_fire() -> np.ndarray:
    dur = 0.15
    wf = square(140, dur) * envelope(int(SAMPLE_RATE * dur), 0.02, 0.3)
    return to_int16_stereo(wf, volume=0.35)


def wave_start() -> np.ndarray:
    """Alternating two-tone alarm, warning of the incoming wave."""
    seg = 0.15
    parts = [
        square(700 if i % 2 == 0 else 500, seg) * envelope(int(SAMPLE_RATE * seg), 0.05, 0.3)
        for i in range(4)
    ]
    return to_int16_stereo(np.concatenate(parts), volume=0.4)


def wave_end_bonus() -> np.ndarray:
    """Short chime marking the start of the end-of-wave tally."""
    dur = 0.3
    wf = sweep(400, 900, dur) * envelope(int(SAMPLE_RATE * dur), 0.05, 0.5)
    return to_int16_stereo(wf, volume=0.4)


def tally_tick() -> np.ndarray:
    dur = 0.04
    wf = square(1200, dur) * envelope(int(SAMPLE_RATE * dur), 0.05, 0.5)
    return to_int16_stereo(wf, volume=0.3)


def bonus_city() -> np.ndarray:
    """Ascending arpeggio; randomized per the disassembly's "series of
    random tones" description."""
    base_freqs = [523.25, 659.25, 783.99, 1046.50]
    freqs = [f * random.uniform(0.97, 1.03) for f in base_freqs]
    seg = 0.12
    parts = [sine(f, seg) * envelope(int(SAMPLE_RATE * seg), 0.02, 0.4) for f in freqs]
    return to_int16_stereo(np.concatenate(parts), volume=0.45)


def game_over() -> np.ndarray:
    """Long descending rumble for the "THE END" screen."""
    dur = 2.0
    n = int(SAMPLE_RATE * dur)
    wf = noise(dur) * 0.3 + sweep(220, 40, dur) * 0.6
    wf *= envelope(n, 0.05, 0.6)
    return to_int16_stereo(wf, volume=0.5)


def flier_drone_loop() -> np.ndarray:
    """Steady tone with slow vibrato, looped while a flier is on screen."""
    dur = 1.0
    t = np.linspace(0.0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    vibrato = 1.0 + 0.15 * np.sin(2 * np.pi * 5 * t)
    wf = sine(220, dur) * vibrato
    return to_int16_stereo(wf, volume=0.22)


def smart_bomb_warble_loop() -> np.ndarray:
    """Fast two-tone warble, looped while a smart bomb is on screen."""
    dur = 0.6
    n = int(SAMPLE_RATE * dur)
    t = np.linspace(0.0, dur, n, endpoint=False)
    freq_t = 400.0 + 60.0 * np.sign(np.sin(2 * np.pi * 8 * t))
    phase = 2 * np.pi * np.cumsum(freq_t) / SAMPLE_RATE
    wf = np.sin(phase)
    return to_int16_stereo(wf, volume=0.25)
