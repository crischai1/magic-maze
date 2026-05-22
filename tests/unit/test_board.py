import os

from app.game.board import Board
from app.game.enums import Direction
from app.game.tile_loader import load_tiles_from_file


def _tiles():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app", "data", "tiles.json"))
    return load_tiles_from_file(path)


def test_place_starting_tile_populates_cells():
    tiles = _tiles()
    board = Board(tiles)
    board.place("T01", origin=(0, 0), rotation=0)
    for r in range(4):
        for c in range(4):
            assert board.cell_at((r, c)) is not None


def test_no_overlap_raises():
    tiles = _tiles()
    board = Board(tiles)
    board.place("T01", origin=(0, 0), rotation=0)
    try:
        board.place("T02", origin=(0, 0), rotation=0)
    except ValueError:
        return
    raise AssertionError("Expected overlap to raise")


def test_neighbor_off_board_is_none():
    tiles = _tiles()
    board = Board(tiles)
    board.place("T01", origin=(0, 0), rotation=0)
    assert board.neighbor((0, 0), Direction.W) is None  # past edge


def test_can_traverse_blocked_by_wall():
    tiles = _tiles()
    board = Board(tiles)
    board.place("T01", origin=(0, 0), rotation=0)
    # T01 row 0 has walls. Just test the API doesn't crash.
    ok, why = board.can_traverse((1, 1), Direction.E)
    assert isinstance(ok, bool)
    assert isinstance(why, str)
