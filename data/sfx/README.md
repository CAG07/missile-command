# Sound Effect Assets

Sound effect assets for POKEY chip audio simulation.

**None of these files are required.** `AudioManager` procedurally
synthesizes every sound with numpy (`src/ui/synth.py`) at startup, so
the game is fully playable with this directory empty. Drop a real
`.wav` file in here (matching a name below) to override the
synthesized version for that specific sound -- loaded files always
take priority over synthesis.

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

### Not in the original channel table
| File | Description |
|------|-------------|
| `roll_up_2.wav` | One tick per surviving city counted up on the tally screen (played first) |
| `roll_up_1.wav` | One tick per unfired ABM counted up on the tally screen (played after cities) |

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
