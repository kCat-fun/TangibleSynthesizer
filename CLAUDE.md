# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python application for controlling toio robot cubes in a musical duet/recording system. It uses two toio cubes connected via Bluetooth to record motion from one cube and play it back or mirror it on a second cube, with real-time audio synthesis based on cube position.

## Development Commands

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Run the application
python src/main.py

# Run tests
pytest .
```

## Architecture

The project follows Clean Architecture with Domain-Driven Design:

```
src/
├── main.py                    # Entry point - CLI application with two modes:
│                              #   Mode 1: Record & playback motion
│                              #   Mode 2: Real-time 2-second delayed mirroring
├── domain/                    # Business logic layer
│   ├── geometry/              # Map positions (3x3 grid coordinates)
│   ├── navigation/            # Movement target calculation
│   └── transport/             # Transport planning (lever-based object pushing)
├── infrastructure/            # External services
│   └── toio/                  # toio cube BLE interface
│       ├── cube_controller.py # Connection management, LED control
│       ├── cube_action.py     # Motor control, movement commands
│       └── cube_sensing.py    # Position & magnetic sensor reading
└── usecase/                   # Orchestration layer (stubs - incomplete)
```

## Key Technical Details

- **Async-first**: Uses asyncio for BLE communication
- **Threading**: Audio synthesis runs in dedicated thread (SynthesizerSound class)
- **Recording rate**: ~50Hz motion capture with threshold-based frame filtering
- **Play mat bounds**: X(45-455), Y(45-455)
- **Position grid**: 3x3 predefined positions defined in `domain/geometry/map_positions.py`

## Dependencies

- toio (robotics library)
- numpy
- pyaudio (audio synthesis)

## Hardware Requirements

Two toio cubes identified by Bluetooth MAC addresses (hardcoded in main.py as `serve_toio` and `recive_toio`).
