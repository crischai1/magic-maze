"""Global board: placed tiles indexed by (row, col), with rotation handling."""
from __future__ import annotations

from typing import Iterator, Optional

from app.game.enums import DIR_VECTOR, Color, Direction, Feature
from app.game.models import PlacedTile, ResolvedCell, TileCellDef, TileDef


def rotate_local(lr: int, lc: int, rotation: int) -> tuple[int, int]:
    """Rotate local cell coords by `rotation` * 90 CW.

    Returns the position of that cell within the rotated tile's grid.
    rotation=0: (lr, lc)
    rotation=1 (90 CW): (lc, 3-lr)
    rotation=2 (180):   (3-lr, 3-lc)
    rotation=3 (270 CW): (3-lc, lr)
    """
    r = rotation % 4
    if r == 0:
        return lr, lc
    if r == 1:
        return lc, 3 - lr
    if r == 2:
        return 3 - lr, 3 - lc
    return 3 - lc, lr


def inverse_rotate_local(gr_in_tile: int, gc_in_tile: int, rotation: int) -> tuple[int, int]:
    """Inverse: given a cell's position in the rotated tile grid, return its local (lr, lc)."""
    r = rotation % 4
    if r == 0:
        return gr_in_tile, gc_in_tile
    if r == 1:
        return 3 - gc_in_tile, gr_in_tile
    if r == 2:
        return 3 - gr_in_tile, 3 - gc_in_tile
    return gc_in_tile, 3 - gr_in_tile


def rotate_direction(d: Direction, rotation: int) -> Direction:
    return Direction((d + rotation) % 4)


class Board:
    """Global grid of placed tiles. Indexes cells by global (row, col)."""

    def __init__(self, tile_registry: dict[str, TileDef]):
        self.tile_registry = tile_registry
        self.placed: list[PlacedTile] = []
        # global (row, col) → PlacedTile (the tile occupying that cell)
        self.cell_to_tile: dict[tuple[int, int], PlacedTile] = {}

    def place(self, tile_id: str, origin: tuple[int, int], rotation: int) -> PlacedTile:
        """Place a tile so its (rotated) cell (0,0) sits at `origin`."""
        if tile_id not in self.tile_registry:
            raise ValueError(f"Unknown tile id {tile_id!r}")
        rotation = rotation % 4
        placed = PlacedTile(tile_id=tile_id, origin=origin, rotation=rotation)
        for r in range(4):
            for c in range(4):
                key = (origin[0] + r, origin[1] + c)
                if key in self.cell_to_tile:
                    raise ValueError(f"Cell {key} already occupied")
                self.cell_to_tile[key] = placed
        self.placed.append(placed)
        return placed

    def has_cell(self, pos: tuple[int, int]) -> bool:
        return pos in self.cell_to_tile

    def cell_at(self, pos: tuple[int, int]) -> Optional[ResolvedCell]:
        tile = self.cell_to_tile.get(pos)
        if tile is None:
            return None
        gr_in_tile = pos[0] - tile.origin[0]
        gc_in_tile = pos[1] - tile.origin[1]
        lr, lc = inverse_rotate_local(gr_in_tile, gc_in_tile, tile.rotation)
        cell_def = self.tile_registry[tile.tile_id].cells[lr][lc]
        # Rotate walls into global directions
        walls = frozenset(rotate_direction(w, tile.rotation) for w in cell_def.walls)
        one_way = tuple(rotate_direction(d, tile.rotation) for d in cell_def.one_way_forbidden)
        # Escalator endpoint
        esc_global: Optional[tuple[int, int]] = None
        if cell_def.escalator_to is not None:
            tlr, tlc = cell_def.escalator_to
            tgr, tgc = rotate_local(tlr, tlc, tile.rotation)
            esc_global = (tile.origin[0] + tgr, tile.origin[1] + tgc)
        explore_edge = rotate_direction(cell_def.explore_edge, tile.rotation) if cell_def.explore_edge is not None else None
        return ResolvedCell(
            global_pos=pos,
            tile=tile,
            local_row=lr,
            local_col=lc,
            walls=walls,
            one_way_forbidden=one_way,
            features=cell_def.features,
            escalator_to_global=esc_global,
            vortex_color=cell_def.vortex_color,
            explore_color=cell_def.explore_color,
            explore_edge=explore_edge,
        )

    def neighbor(self, pos: tuple[int, int], direction: Direction) -> Optional[tuple[int, int]]:
        dr, dc = DIR_VECTOR[direction]
        target = (pos[0] + dr, pos[1] + dc)
        return target if self.has_cell(target) else None

    def can_traverse(self, from_pos: tuple[int, int], direction: Direction) -> tuple[bool, str]:
        """Check if pawn at `from_pos` can move in `direction`. Returns (ok, reason_if_not)."""
        from_cell = self.cell_at(from_pos)
        if from_cell is None:
            return False, "no source cell"
        if direction in from_cell.walls:
            return False, "wall in front"
        if direction in from_cell.one_way_forbidden:
            return False, "one-way arrow blocks exit"
        target = self.neighbor(from_pos, direction)
        if target is None:
            return False, "edge of board"
        target_cell = self.cell_at(target)
        if target_cell is None:
            return False, "off board"
        if direction.opposite() in target_cell.walls:
            return False, "wall on far side"
        return True, ""

    def all_cells(self) -> Iterator[ResolvedCell]:
        for pos in self.cell_to_tile:
            cell = self.cell_at(pos)
            if cell is not None:
                yield cell

    def find_feature(self, feature: Feature) -> list[tuple[int, int]]:
        return [c.global_pos for c in self.all_cells() if feature in c.features]

    def find_vortexes(self, color: Color) -> list[tuple[int, int]]:
        return [c.global_pos for c in self.all_cells() if c.vortex_color == color]

    def find_explore_anchor(self, color: Color, only_unexplored: bool = True) -> list[tuple[int, int]]:
        anchors = []
        for c in self.all_cells():
            if c.explore_color != color:
                continue
            if only_unexplored and c.global_pos in c.tile.explored_anchors:
                continue
            anchors.append(c.global_pos)
        return anchors

    def to_dict(self) -> list[dict]:
        return [
            {
                "tile_id": t.tile_id,
                "origin": list(t.origin),
                "rotation": t.rotation,
                "explored_anchors": [list(p) for p in t.explored_anchors],
            }
            for t in self.placed
        ]
