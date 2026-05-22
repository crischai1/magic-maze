# Co-Op Maze Heist — Handoff Notes

A web-based, real-time, cooperative reimplementation of the board game **Magic Maze** (Sit Down! Games, designer Kasper Lapp). Flask backend (with Flask-SocketIO over eventlet), vanilla-JS frontend rendering an inline SVG board, no build step. All artwork is original SVG drawn from primitives — no scanned or recreated tile illustrations from the published game.

The deployed name is **"Co-Op Maze Heist"** to avoid trademark issues. Internally we call it Magic Maze in commits and docs.

---

## Status

### What works
- **Lobbies**: 4-character base32 room codes, multiple concurrent games, host promotion on disconnect.
- **Real-time multiplayer**: Flask-SocketIO + eventlet, one greenthread per active game broadcasting at 5 Hz.
- **Core game mechanics**:
  - Random hero placement on the starting tile's 4 START squares.
  - Action-card distribution by player count (1–8); a 1-player game gets all 7 actions on one card.
  - **Movement**: WASD = single step; click a highlighted square to slide multi-cell (rulebook allows sliding any distance).
  - **Hero collision**: pawns block each other; can't share a square.
  - **Vortex**: teleports any hero from anywhere to any matching-color vortex; permanently locks the moment the theft fires.
  - **Escalator**: paired-cell jumps within a tile.
  - **Theft trigger**: phase 1 → phase 2 fires only when **all 4 heroes are simultaneously on their item squares**.
  - **Exit**: each hero escapes through its matching-color exit; win when all 4 exit.
  - **Sand Timer**: one-use squares; flipping inverts remaining (elapsed becomes remaining) and opens a chat window.
  - **Chat**: hard-locked by default; unlocks for a window when a Sand Timer is flipped; closes again on the next action.
  - **Exploration**: matching-color hero stepping on an explore door triggers tile placement; auto-rotation picks the only legal orientation; both source and destination doors are marked used and disappear from the render.
  - **Crystal Ball**: when the Mage explores from a Crystal Ball cell, they get 2 tile placements in a row (scenario 5+).
- **Frontend**: SVG board with hero-colored door glyphs (pentagon arrows pointing outward); WASD + mouse input; sidebar with timer / action card / players / chat; a server-driven legend on the home page explaining every square type.
- **Tests**: 65 unit tests passing, covering rotation math, action distribution, timer (including flip math), board, wall symmetry, door reachability, tile/scenario loaders, validator rules, and the client-shape serialization contract.

### What's incomplete / not modeled

- **Scenarios authored**: 1, 2, 3, 4, 5, 6, 7, 14, 16 in [app/data/scenarios.json](app/data/scenarios.json). Scenarios 8–13, 15, 17 are not yet written. The data-driven scenario framework supports them — adding a scenario is mostly a JSON edit plus, if needed, a new rule predicate.
- **Scenario rules declared but not fully enforced**:
  - `pass_left_on_flip` (scenario 3+) — action cards must rotate to the left on each Sand Timer flip; not yet wired into the timer-flip handler.
  - `camera` — Security Camera squares exist as a Feature, but the rule "2+ active cameras block Sand Timer flips" only partially fires (the move-validator branch in `move_validator.py` is hooked up but the camera-disable handler is not fully tested).
  - `dwarf_passage` — Feature exists; the Dwarf-only traversal check is not implemented in the validator yet.
  - `elf_explore_talks` — partly wired in `commit_exploration` but the close-on-next-action edge case isn't covered.
- **Manual tile-rotation UI for exploration**: the server auto-picks the only legal orientation. The published game lets the explorer choose orientation when more than one fits.
- **Integration tests** (`tests/integration/`): the directory exists but no socket-test_client scripts have been written. There's no end-to-end "scripted moves solve scenario 1" test yet.
- **Disconnect/reconnect**: a player who drops loses their slot (pre-game) or stays disconnected in-game; reconnect via the same `player_id` cookie reattaches the slot but the action card is not transferable on disconnect (real rulebook: "actions become temporarily shared with neighbors").
- **Persistence**: all state is in-process Python dicts. Server restart drops everything. `Game.snapshot()` is set up to make a future Redis swap easy.
- **Mobile**: the SVG board responds to viewport changes but hasn't been tuned for touch input.
- **"No talking" enforcement**: only in-game chat is locked. External chat (Discord, voice) is on the honor system. Stated as a known limitation in [README.md](README.md).

### Tile data

11 tiles in [app/data/tiles.json](app/data/tiles.json). The published game has 24+. Each authored tile has 4 colored explore doors on the perimeter (one per edge, except T04 and T10 which are restrictive corridors). Adding more tiles is a JSON edit; the loader normalizes walls symmetrically and the test suite checks for sealed doors and asymmetric walls.

---

## Quickstart

```bash
# From the project root:
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Run the dev server (port 5001 by default; override with PORT env var):
.venv/bin/python run.py
# → http://localhost:5001

# Run tests:
.venv/bin/python -m pytest tests/ -q
```

To play multiplayer locally, open 2+ browser tabs in different profiles or private windows (so the session cookies differ). Create a lobby in one, share the 4-char code, join from the others.

---

## Architecture

```
magic-maze/
├── run.py                         # eventlet.monkey_patch() MUST be the first line
├── pyproject.toml
├── README.md                      # user-facing run instructions
├── handoff.md                     # this file
├── app/
│   ├── __init__.py                # create_app() — loads tiles/scenarios into LobbyManager
│   ├── config.py                  # Config class
│   ├── extensions.py              # socketio singleton + LobbyManager singleton
│   ├── session.py                 # player_id cookie + username helpers
│   ├── lobby_routes.py            # Flask Blueprint: /, /lobby/<code>, /game/<code>
│   ├── sockets.py                 # ALL SocketIO event handlers (namespace /game)
│   │
│   ├── game/                      # Pure Python; NO Flask imports — fully unit-testable
│   │   ├── enums.py               # Color (Y/P/G/O), Direction (IntEnum), ActionType,
│   │   │                          #   Feature, Phase (EXPLORING/ESCAPING/FINISHED), Outcome
│   │   ├── models.py              # TileDef, TileCellDef, PlacedTile (with
│   │   │                          #   explored_anchors: Set), Pawn, ActionTile,
│   │   │                          #   Player, ScenarioConfig
│   │   ├── tile_loader.py         # JSON → TileDef; includes _normalize_walls() that
│   │   │                          #   symmetrizes walls and forces perimeter walls
│   │   ├── board.py               # Global grid + tile rotation math.
│   │   │                          #   cell_at() resolves to ROTATED form on demand.
│   │   ├── action_tiles.py        # Distribution table for 1–8 players
│   │   ├── timer.py               # SandTimer: tick, flip (invert), bonus, pause/resume
│   │   ├── deltas.py              # All delta-op dataclasses + Enum→primitive to_dict()
│   │   ├── move_validator.py      # validate_move() = single source of truth for legal
│   │   │                          #   moves. Helpers: reachable_slide_targets,
│   │   │                          #   check_theft_trigger, check_exit_trigger
│   │   ├── game.py                # Game class: orchestrates start, apply_move,
│   │   │                          #   begin_exploration, commit_exploration, tick,
│   │   │                          #   snapshot. Stateless aside from self.
│   │   ├── lobby.py               # Lobby + LobbyManager (room codes, host, etc.)
│   │   └── scenarios.py           # ScenarioConfig loader
│   │
│   ├── data/
│   │   ├── tiles.json             # 11 tiles (1 start + 10 deck)
│   │   └── scenarios.json         # 9 of the 17 published scenarios
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html             # Home: username, create/join, hero+square-types legend
│   │   ├── lobby.html             # Waiting room; live-updated via SocketIO
│   │   └── game.html              # Board + sidebar; <defs> for all SVG glyphs
│   │
│   └── static/
│       ├── css/
│       │   ├── base.css           # Color variables, layout, home/lobby styles, legend
│       │   ├── board.css          # Board pane, cells, walls, pawns, move hints
│       │   └── ui.css             # Sidebar, timer, action card, chat
│       └── js/
│           ├── lobby.js           # Lobby page (player list, scenario picker, start btn)
│           └── game.js            # SVG renderer, state, input, network — all in one
│                                  #   file. Imports nothing; pure ES script.
└── tests/
    ├── conftest.py
    └── unit/
        ├── test_action_tile_distribution.py
        ├── test_board.py
        ├── test_door_reachability.py
        ├── test_rotation.py
        ├── test_rules.py
        ├── test_scenario_loader.py
        ├── test_tile_def_serialization.py    # CRITICAL: locks the client contract
        ├── test_tile_loader.py
        ├── test_timer.py
        ├── test_wall_symmetry.py
        └── (no integration tests yet)
```

### Request lifecycle

1. Browser hits `/` → Flask renders [index.html](app/templates/index.html). The `before_app_request` hook sets a `player_id` cookie (uuid4) if missing.
2. POST `/` with `action=create` → `LobbyManager.create_lobby()` allocates a 4-char code, returns 302 to `/lobby/<code>`.
3. Browser fetches `/lobby/<code>` → server renders [lobby.html](app/templates/lobby.html) including a list of available scenarios.
4. Browser script connects to SocketIO `/game` namespace, emits `lobby:join` with `{code, username}`. Server adds the player; broadcasts `lobby:state` to the room.
5. Host clicks Start → `lobby:start` → `LobbyManager.start_game()` constructs a `Game`, places the start tile, places pawns randomly on START cells, distributes action cards, starts a 5 Hz `game_loop` greenthread.
6. Server emits `game:snapshot` to all players, then `lobby:redirect_to_game`. Browsers navigate to `/game/<code>`.
7. From here it's deltas. Client emits `game:move` / `game:explore` / `game:explore_commit` / `game:chat` / `game:reachable`. Server validates, applies, broadcasts `game:delta` (and `game:tick` 5 Hz for timer updates).

---

## Key invariants you must not break

These are the load-bearing assumptions; tests enforce them.

1. **`Direction` is serialized as `.name` (string), never `.value` (int).** The client looks up `dirNumByName["N"]` etc. — if you send numbers, walls render as garbage and door rotation breaks. Locked by [test_tile_def_serialization.py](tests/unit/test_tile_def_serialization.py). The two emit sites are `Game._tile_defs_for_placed` in [game.py](app/game/game.py) and `_serialize_tile_def` in [sockets.py](app/sockets.py).

2. **Walls are symmetric.** If cell (r,c) has E wall, cell (r,c+1) MUST have W wall. The tile loader's `_normalize_walls` in [tile_loader.py](app/game/tile_loader.py) enforces this at load time — you can author asymmetric walls in JSON and it fixes them. Locked by [test_wall_symmetry.py](tests/unit/test_wall_symmetry.py).

3. **Door cells must connect to the tile interior.** A door cell encoded as `"####:xy"` is a 1-cell dead-end. Use `"....:xy"` and let the loader strip the door-direction perimeter wall. Locked by [test_door_reachability.py](tests/unit/test_door_reachability.py).

4. **`eventlet.monkey_patch()` is the first line of [run.py](run.py).** It must run before any import that touches `socket`, `ssl`, `threading`, etc. Otherwise SocketIO will silently use the wrong async backend.

5. **`PlacedTile.explored_anchors` is a `set[tuple[int,int]]`**, not an Optional. Both the source door (on the previous tile) AND the entrance door (on the new tile) get added when an exploration commits, so both glyphs disappear and neither can re-trigger.

6. **`Color` and `Feature` are `str`-Enums; `Direction` is `IntEnum`.** Their `.value` properties differ in type — be careful when serializing. Rule: serialize Color/Feature via `.value` (gives a string); serialize Direction via `.name` (gives `"N"/"E"/"S"/"W"`).

7. **Per-tick game-loop work must be O(1).** Eventlet is cooperative — a slow tick handler stutters every game on the worker. Move heavy work (snapshot serialization, big iterations) outside the 5 Hz loop. The current loop only decrements the timer, expires chat windows, and emits a thin payload.

8. **Move validation is the single source of truth.** Never apply a move outside `validate_move()` (and `apply_move()` which wraps it). Direct mutations of `pawn.pos` etc. will desync the version counter and clients will request resyncs.

---

## Where to look first when something is wrong

| Symptom | First place to check |
|---|---|
| Walls look weird / appear randomly | Direction serialization in `game.py:_tile_defs_for_placed` and `sockets.py:_serialize_tile_def`. Run `test_tile_def_serialization.py`. |
| Doors don't rotate / sit at cell centers | Same as walls — `explore_edge` must be serialized as `.name`. |
| Hero can't enter a door cell | The cell's outer wall in the door direction might still be `#`. The loader should normalize, but check `_normalize_walls` ran. |
| Exploration places the new tile but no doors disappear | `PlaceTileOp.entrance_anchor` not being set or not being propagated to the client's `markCellExplored` helper. |
| Timer flip resets to full instead of inverting | `SandTimer.flip()` (in `timer.py`) should compute `elapsed = starting_ms - remaining_ms; remaining_ms = elapsed`. There are 3 tests for this. |
| Theft fires when only some heroes have items | The trigger is in `move_validator.check_theft_trigger()` and must check the heroes' CURRENT positions, not their `has_item` flags. |
| Server log says `eventlet` deprecated warning | Harmless. Eventlet is in maintenance mode; we use it because it's the most reliable async mode for Flask-SocketIO right now. |
| Cell-bg has visible grid lines | Don't add `stroke` to `.cell-bg` in [board.css](app/static/css/board.css). The thick white `.cell-wall` lines should be the only visible separators. |

---

## What to do next (rough priority)

1. **Finish scenario rules** (declared in `extra_rules` but not enforced):
   - `pass_left_on_flip` — wire into the `TimerFlipOp` handler in `game.py`.
   - `dwarf_passage` — add a check in `move_validator.validate_move` (Dwarf bypasses passage walls).
   - `camera` — finish the 2+ active cameras → block Sand Timer rule.
2. **Manual tile-rotation UI for exploration.** Server should broadcast all legal rotations on `RequireExplorationOp`; client lets the explorer cycle with a key (R) and click to confirm.
3. **More tiles.** 13 more to get to the published count. Add at runtime via JSON; the loader handles everything.
4. **Integration tests.** `tests/integration/` is empty. The lowest-friction approach is Flask-SocketIO's `socketio.test_client(app)` driving two clients through a scripted game.
5. **Reconnect polish.** When a player disconnects mid-game their action card should become temporarily shared with the rest of the table (per rulebook). Right now their slot just goes dormant.
6. **Mobile.** SVG already scales; needs touch-input handling and a responsive sidebar.
7. **Sound cues.** Tile placement, theft, exit, time-out — small original WAV/OGG samples would help "no talking" feel right.
8. **Persistence.** Swap `LobbyManager`'s in-memory dicts for a Redis-backed implementation behind the same interface; `Game.snapshot()` is already suitable.

---

## Known limitations / accepted compromises

- **In-process memory only.** Server restart drops every active game. Acceptable for v1.
- **External chat is unenforceable.** We hard-lock the in-game chat; we can't stop voice calls or Discord. Stated in the README.
- **Tile artwork is original.** We deliberately don't use any scanned imagery from the published game. The visual style is functional, not a recreation.
- **The deployed name is "Co-Op Maze Heist."** Don't put "Magic Maze" in the page title, meta tags, or marketing — that's a registered product name belonging to Sit Down! Games.
- **Eventlet is in bugfix-mode upstream.** Long-term we should look at migrating to async-mode `asyncio` or `gevent`. Not urgent.

---

## A few useful one-liners

```bash
# Run only the rule-correctness tests:
.venv/bin/python -m pytest tests/unit/test_rules.py tests/unit/test_wall_symmetry.py tests/unit/test_door_reachability.py -v

# Inspect what the server actually serializes:
.venv/bin/python -c "from app.game.game import Game; from app.game.scenarios import load_scenarios; from app.game.tile_loader import load_tiles_from_file; from app.game.models import Player; import json, os; t=load_tiles_from_file('app/data/tiles.json'); s=load_scenarios('app/data/scenarios.json'); g=Game('X', s[1], [Player('p','P')], t, seed=1); g.start(); print(json.dumps(g.snapshot()['board']['tile_defs']['T01'], indent=2))"

# Render a tile's wall layout as ASCII (useful when authoring):
.venv/bin/python -c "
from app.game.enums import Direction
from app.game.tile_loader import load_tiles_from_file
t = load_tiles_from_file('app/data/tiles.json')['T01']
print('+' + '+'.join('---' if Direction.N in t.cells[0][c].walls else '   ' for c in range(4)) + '+')
for r in range(4):
    row = '|' if Direction.W in t.cells[r][0].walls else ' '
    for c in range(4):
        row += ' . ' + ('|' if Direction.E in t.cells[r][c].walls else ' ')
    print(row)
    sep = '+' + '+'.join('---' if Direction.S in t.cells[r][c].walls else '   ' for c in range(4)) + '+'
    print(sep)
"
```

---

## Source for the rules

The Magic Maze rulebook (English, Sept 2018, published by Sit Down! Games) is the authoritative reference: https://sitdown-games.com/wp-content/uploads/2018/09/MM_Rules_EN_HR_Sept2018_LD.pdf

Specifically informed by the rulebook (and verified against it during recent fixes):
- Hero colors and roles (Barbarian=Yellow, Mage=Purple, Elf=Green, Dwarf=Orange).
- Movement: slide any number of squares until hitting a wall, edge, or other hero.
- Theft: all 4 heroes on item squares simultaneously.
- Vortex: teleport from anywhere to any matching-color vortex; permanently disabled after theft.
- Sand Timer: physical flip — elapsed becomes remaining.
- Communication: locked except briefly when a Sand Timer flips.

The full architecture rationale and a recent "Visual Faithfulness Pass" iteration are in the plan file at `~/.claude/plans/create-an-online-version-playful-gizmo.md`.
