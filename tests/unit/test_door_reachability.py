"""Every explore-door cell on every tile must connect to the rest of the
tile's interior. A door cell that's sealed off (e.g. encoded as "####:xy")
becomes a dead-end: heroes walk into it through the door and can't go anywhere.
This guarantees the tile design is actually playable.
"""
import os

import pytest

from app.game.board import Board
from app.game.enums import Direction
from app.game.tile_loader import load_tiles_from_file

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app", "data"))


@pytest.fixture
def tiles():
    return load_tiles_from_file(os.path.join(DATA_DIR, "tiles.json"))


def _bfs_reachable(board: Board, start: tuple[int, int]) -> set[tuple[int, int]]:
    """All cells reachable from `start` within the same tile via interior walls."""
    seen = {start}
    frontier = [start]
    while frontier:
        pos = frontier.pop()
        for d in Direction:
            ok, _ = board.can_traverse(pos, d)
            if not ok:
                continue
            nxt = board.neighbor(pos, d)
            if nxt is None or nxt in seen:
                continue
            seen.add(nxt)
            frontier.append(nxt)
    return seen


def test_every_door_cell_connects_to_at_least_one_neighbor(tiles):
    """At least one interior neighbor must be reachable from each door cell."""
    failures = []
    for tile_id, tile in tiles.items():
        board = Board(tiles)
        board.place(tile_id, origin=(0, 0), rotation=0)
        for r in range(4):
            for c in range(4):
                cell_def = tile.cells[r][c]
                if cell_def.explore_color is None:
                    continue
                # Each Direction except the explore_edge: try to traverse.
                # At least ONE must succeed (so the door cell has an interior link).
                interior_links = 0
                for d in Direction:
                    if d == cell_def.explore_edge:
                        continue
                    ok, _ = board.can_traverse((r, c), d)
                    if ok:
                        interior_links += 1
                if interior_links == 0:
                    failures.append(
                        f"{tile_id} door cell at ({r},{c}) facing "
                        f"{cell_def.explore_edge.name if cell_def.explore_edge else '?'} "
                        f"is SEALED — hero would be stuck."
                    )
    assert not failures, "Sealed door cells:\n  " + "\n  ".join(failures)


def test_every_door_cell_reaches_at_least_two_cells(tiles):
    """A door cell must reach at least one other cell — otherwise the hero
    walks through the door and is stuck (no way to traverse or exit).
    Corridor/restrictive designs are fine (they may only reach a few cells),
    but a door reaching only itself is a sealed-off bug.
    """
    failures = []
    for tile_id, tile in tiles.items():
        board = Board(tiles)
        board.place(tile_id, origin=(0, 0), rotation=0)
        for r in range(4):
            for c in range(4):
                cell_def = tile.cells[r][c]
                if cell_def.explore_color is None:
                    continue
                reachable = _bfs_reachable(board, (r, c))
                if len(reachable) < 2:
                    failures.append(
                        f"{tile_id} door at ({r},{c}) is sealed "
                        f"(reaches only {sorted(reachable)})"
                    )
    assert not failures, "Sealed door:\n  " + "\n  ".join(failures)
