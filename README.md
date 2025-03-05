# Missile Command 🚀🎮

## Overview

A faithful recreation of the classic 1980 Atari arcade game, Missile Command, implemented in Python. This project aims to capture the intense strategic gameplay of defending cities from nuclear missile attacks while staying true to the original game's mechanics.

![Game Screenshot](missile-command\Missile_Command.png)

## Background

Missile Command is a legendary arcade game developed by Atari, Inc. in 1980, designed by Dave Theurer. The Atari 2600 port by Rob Fulop became a massive success, selling over 2.5 million copies and becoming the third most popular cartridge for the system.

## Game Narrative

You are the Missile Commander of the Missile Intercept Launch Function, tasked with an critical mission: protect six cities from total annihilation during a nuclear war. With nuclear warheads raining down and millions of lives at stake, your lightning-fast reflexes and precise aiming are humanity's last hope.

## Features

- Authentic recreation of the classic Missile Command gameplay
- Pixel-perfect missile and explosion mechanics
- Challenging wave-based enemy missile attacks
- Responsive mouse-based controls
- Detailed sound and visual effects

## Prerequisites

- Python 3.8+
- pip
- pipenv (optional, but recommended)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/missile-command.git
cd missile-command
```

2. Create a virtual environment and install dependencies:
```bash
# If you don't have pipenv
pip install pipenv

# Create and activate virtual environment
pipenv shell

# Install dependencies
pipenv install -r requirements.txt
```

## Running the Game

```bash
python missile-defense.py
```

## Game Controls

- **Mouse Movement**: Aim targeting cursor
- **Primary Mouse Button**: Fire interceptor missile
- **Escape Key**: Pause/Exit game

## Project Structure

missile-command/
│
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── game.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── defence.py
│   │   ├── missile.py
│   │   ├── city.py
│   │   └── explosion.py
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── functions.py
│   │   └── input_handler.py
│   │
│   └── ui/
│       ├── __init__.py
│       └── text.py
│
├── data/
│   ├── fnt/
│   ├── img/
│   └── sfx/
│
├── tests/
│   ├── test_missile.py
│   ├── test_defence.py
│   └── test_game.py
│
├── requirements.txt
├── README.md
└── main.py

## Development Roadmap

- [x] Basic game mechanics
- [ ] Implement score tracking
- [ ] Add difficulty progression
- [ ] Enhance sound effects
- [ ] Create advanced enemy missile patterns

## References

- [Original Missile Command Wikipedia Article](https://en.wikipedia.org/wiki/Missile_Command)
- Missile Command Disassembly.pdf (Atari 2600 version reference)

## Acknowledgments

- Inspired by the original Atari Missile Command
- Based on initial work by BekBrace
- Special thanks to the original game designers at Atari

## Contact

Project Link: [https://github.com/CAG07/missile-command](https://github.com/CAG07/missile-command)
