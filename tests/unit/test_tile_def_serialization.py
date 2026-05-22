"""The client-side renderer (game.js) expects walls and explore_edge as
direction NAMES ("N"/"E"/"S"/"W"), not the numeric Direction.value. If the
server serializes the int, the client's dirNumByName[w] lookup returns
undefined and walls render as the default W line at every cell (the "walls
randomly placed" symptom) and doors don't rotate.
"""
import json
import os

import pytest

from app.game.action_tiles import ALL_ACTIONS
from app.game.enums import Color
from app.game.game import Game
from app.game.models import ActionTile, Player
from app.game.scenarios import load_scenarios
from app.game.tile_loader import load_tiles_from_file
from app.sockets import _serialize_tile_def

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app", "data"))


def _game():
    tiles = load_tiles_from_file(os.path.join(DATA_DIR, "tiles.json"))
    scenarios = load_scenarios(os.path.join(DATA_DIR, "scenarios.json"))
    p = Player(player_id="p0", username="P")
    g = Game("TEST", scenarios[1], [p], tiles, seed=1)
    g.start()
    p.action_tile = ActionTile(actions=frozenset(ALL_ACTIONS))
    return g, tiles


def test_snapshot_walls_use_direction_name_strings():
    g, _ = _game()
    snap = g.snapshot()
    tile_defs = snap["board"]["tile_defs"]
    assert "T01" in tile_defs
    seen_walls = []
    for row in tile_defs["T01"]["cells"]:
        for cell in row:
            seen_walls.extend(cell["walls"])
    # All wall entries must be one of N/E/S/W (strings), not ints 0..3
    assert all(isinstance(w, str) and w in {"N", "E", "S", "W"} for w in seen_walls), (
        f"Walls must be direction-name strings; got: {seen_walls[:8]}"
    )


def test_snapshot_explore_edge_is_a_direction_name_string():
    g, _ = _game()
    snap = g.snapshot()
    tile_defs = snap["board"]["tile_defs"]
    found_an_edge = False
    for row in tile_defs["T01"]["cells"]:
        for cell in row:
            ee = cell["explore_edge"]
            if ee is None:
                continue
            found_an_edge = True
            assert isinstance(ee, str) and ee in {"N", "E", "S", "W"}, (
                f"explore_edge must be a direction-name string; got: {ee!r}"
            )
    assert found_an_edge, "Starting tile should declare at least one explore_edge"


def test_delta_serialize_tile_def_uses_strings():
    _, tiles = _game()
    t02 = tiles["T02"]
    sd = _serialize_tile_def(t02)
    for row in sd["cells"]:
        for cell in row:
            for w in cell["walls"]:
                assert isinstance(w, str) and w in {"N", "E", "S", "W"}
            if cell["explore_edge"] is not None:
                assert isinstance(cell["explore_edge"], str)
                assert cell["explore_edge"] in {"N", "E", "S", "W"}


def test_snapshot_round_trips_through_json():
    """The whole snapshot must be json-serializable as-is — no Direction enum
    leakage that would crash JSON encoding."""
    g, _ = _game()
    snap = g.snapshot()
    blob = json.dumps(snap)  # would raise if any Enum slipped through
    parsed = json.loads(blob)
    assert parsed["board"]["tile_defs"]["T01"] is not None
