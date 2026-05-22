# Co-Op Maze Heist

A real-time cooperative tile-exploration game inspired by **Magic Maze** (Sit Down! Games, designer Kasper Lapp). Up to 8 players control 4 heroes through a maze of tiles, each player limited to a subset of actions, racing against a sand timer — and forbidden to talk except when the maze grants them a brief reprieve.

This implementation is original code with original SVG artwork. It is fan-made, not affiliated with or endorsed by the publisher.

## Status

Playable MVP — Scenarios 1–4 (basic heist, crystal balls, do-anything chat windows, speed run). Tile exploration, vortexes, escalators, win/loss, and chat-lock all work.

Future work: scenarios 5–17, ghost-tile rotation UI for exploration, reconnect handling, mobile polish.

## How to run

```bash
# 1. Create a virtual environment and install dependencies
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2. Run the dev server
.venv/bin/python run.py

# 3. Open the app in two or more tabs
open http://localhost:5000
```

Use distinct browser profiles or private windows for each "player" so the session cookies differ.

### Playing

1. Pick a name and create a lobby. Share the 4-character code.
2. Other players go to `/`, enter the code, and join.
3. The host picks a scenario and clicks **Start**.
4. **Click a pawn**, then click a highlighted adjacent square *or* press one of the action keys:
   - `W`/`A`/`S`/`D` — move N/W/S/E (if your action card permits)
   - `E` — escalator
   - `V` — vortex (color-matched, locked once any item is stolen)
   - `X` — explore (place the next tile when standing on a matching anchor)
   - `1`/`2`/`3`/`4` — quick-select Red/Blue/Green/Yellow pawn
5. Phase 1: walk each hero to their matching-color shop. Phase 2: walk all four to the matching exits.
6. **No talking.** The chat box is locked unless a hero steps on a "Do anything" square. Talking aloud or via outside chat works on the honor system.

## Running tests

```bash
.venv/bin/pytest
```

## Architecture

- **Backend**: Flask + Flask-SocketIO (eventlet async).
- **State**: In-process Python dicts keyed by lobby code. Lost on restart.
- **Frontend**: Vanilla ES modules + Jinja2 templates. No build step.
- **Board**: Inline SVG, layered groups for tiles / pawns / overlays.
- **Game logic**: `app/game/` is pure Python with no Flask imports — fully unit-testable.

Key files:

- `app/game/game.py` — central `Game` class.
- `app/game/move_validator.py` — single source of truth for legal moves.
- `app/game/board.py` — global grid + tile rotation math.
- `app/sockets.py` — every client interaction.
- `app/data/tiles.json` — 11 authored tiles (start + 10 deck tiles).
- `app/data/scenarios.json` — 4 scenarios.
- `app/static/js/game.js` — SVG renderer + input + network.

## Known limitations

- "No talking" can't be enforced beyond locking the in-game chat. Outside channels (Discord, voice) are on the honor system.
- Tile exploration auto-rotates to the only legal orientation; no manual rotation UI yet.
- Server restart drops all games (no persistence). `Game.snapshot()` makes a future Redis swap easy.
- Only 11 tiles authored; full Magic Maze has 24+. The data format is set up to accept more.
