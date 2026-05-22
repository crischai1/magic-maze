"""Walls must be symmetric — if cell (r,c) has wall on E, then cell (r,c+1)
must have wall on W (and vice versa). Otherwise rendering and movement
validation will disagree on whether the wall exists.
"""
import os

import pytest

from app.game.enums import Direction
from app.game.tile_loader import load_tiles_from_file

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app", "data"))


@pytest.fixture
def tiles():
    return load_tiles_from_file(os.path.join(DATA_DIR, "tiles.json"))


def test_all_walls_are_symmetric(tiles):
    """For every adjacent pair of interior cells in every tile, walls match on both sides."""
    failures = []
    for tile_id, tile in tiles.items():
        for r in range(4):
            for c in range(4):
                cell = tile.cells[r][c]
                # East/west symmetry
                if c < 3:
                    neighbor = tile.cells[r][c + 1]
                    e_here = Direction.E in cell.walls
                    w_there = Direction.W in neighbor.walls
                    if e_here != w_there:
                        failures.append(
                            f"{tile_id} ({r},{c}).E={e_here} but ({r},{c+1}).W={w_there}"
                        )
                # North/south symmetry
                if r < 3:
                    neighbor = tile.cells[r + 1][c]
                    s_here = Direction.S in cell.walls
                    n_there = Direction.N in neighbor.walls
                    if s_here != n_there:
                        failures.append(
                            f"{tile_id} ({r},{c}).S={s_here} but ({r+1},{c}).N={n_there}"
                        )
    assert not failures, "Asymmetric walls found:\n  " + "\n  ".join(failures)


def test_each_tile_has_at_least_one_explore_door(tiles):
    for tile_id, tile in tiles.items():
        if tile.is_starting:
            continue
        has_door = any(
            cell.explore_color is not None
            for row in tile.cells
            for cell in row
        )
        assert has_door, f"Tile {tile_id} has no explore door"


def test_explore_doors_have_open_outer_wall(tiles):
    """An explore door cell should have its explore_edge wall OPEN (not a wall)."""
    for tile_id, tile in tiles.items():
        for r in range(4):
            for c in range(4):
                cell = tile.cells[r][c]
                if cell.explore_color is None or cell.explore_edge is None:
                    continue
                assert cell.explore_edge not in cell.walls, (
                    f"{tile_id} ({r},{c}) is an explore door facing {cell.explore_edge.name} "
                    f"but that direction is walled"
                )
