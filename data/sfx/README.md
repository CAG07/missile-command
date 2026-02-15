# Sound Effect Assets

Sound effect assets for POKEY chip audio simulation.

## Channel Assignments

The original arcade uses 4 independent sound channels (POKEY chip).

### Channel 1
| File | Description |
|------|-------------|
| `silo_low.wav` | Warning when silo running low on ABMs |
| `slam.wav` | High-pitched sound when slam switch triggered |

### Channel 2
| File | Description |
|------|-------------|
| `explosion.wav` | Explosion sound |

### Channel 3
| File | Description |
|------|-------------|
| `abm_launch.wav` | Player fires ABM |
| `bonus_city.wav` | Series of random tones on bonus city award |

### Channel 4
| File | Description |
|------|-------------|
| `bonus_points.wav` | End of wave scoring |
| `start_wave.wav` | Wave beginning |
| `game_over.wav` | Game end |
| `cant_fire.wav` | Attempted fire with no ABMs |
| `flier.wav` | Continuous sound when flier active |
| `smart_bomb.wav` | Continuous sound when smart bomb active |

## Audio Format

- WAV format (pygame native support)
- 22050 Hz or 44100 Hz sample rate
- Mono, 16-bit depth
- Keep file sizes small (authentic to chip audio)

## Behavior Notes

- New sounds replace older sounds on same channel
- Flier/bomb sound interrupted by warnings, then resumes
- If both flier and bomb present, only bomb sound plays
- Bonus city sound is randomized tones, not fixed
- Continuous sounds (flier, smart bomb) loop

## Attribution

Place sound asset attribution and licensing information here.
