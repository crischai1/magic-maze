import os

from app.game.tile_loader import load_tiles_from_file


def test_loads_all_authored_tiles():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "app", "data", "tiles.json")
    tiles = load_tiles_from_file(os.path.abspath(path))
    assert "T01" in tiles
    assert tiles["T01"].is_starting
    # All tiles should be 4x4
    for tid, t in tiles.items():
        assert len(t.cells) == 4
        assert all(len(row) == 4 for row in t.cells)
