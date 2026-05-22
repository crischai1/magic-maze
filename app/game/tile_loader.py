"""Parse compact JSON tile definitions into TileDef objects.

Cell encoding: "NESW[:feat1,feat2]"
  - Wall slots are 4 chars in N/E/S/W order; "." = open, "#" = wall.
  - Optional ":feature_codes" appended after the wall string.

Feature codes (hero colors: Y=Yellow Barbarian, P=Purple Mage, G=Green Elf, O=Orange Dwarf):
  iy/ip/ig/io   Item space (where a hero steals their item)
  ey/ep/eg/eo   Exit space (matching-color hero escapes here)
  vy/vp/vg/vo   Vortex (teleport destination, color-matched)
  xy/xp/xg/xo   Exploration anchor (only matching-color hero triggers exploration)
  st            Starting central square (any hero may begin here, placed randomly)
  t             Sand Timer space (one-use; flips timer and opens chat)
  c             Crystal Ball (Mage-only effect from scenario 5+)
  cam           Security Camera (yellow tile; Barbarian disables)
  dp            Dwarf passage (orange wall a Dwarf may pass through; modeled as feature)

Per-tile JSON shape:
  {
    "id": "T01",
    "is_starting": true,
    "cells": [
      ["....", "....:iy", ...],
      ...
    ],
    "escalators": [[[r1,c1],[r2,c2]], ...],
    "edges": { "E": [{"col":3,"row":2}], ... }  # explore anchors on tile edges
  }
"""
from __future__ import annotations

import json
from pathlib import Path

from app.game.enums import Color, Direction, Feature
from app.game.models import TileCellDef, TileDef

WALL_CHARS_ORDER = (Direction.N, Direction.E, Direction.S, Direction.W)

_FEATURE_CODE_MAP: dict[str, Feature] = {
    "iy": Feature.ITEM_Y, "ip": Feature.ITEM_P, "ig": Feature.ITEM_G, "io": Feature.ITEM_O,
    "ey": Feature.EXIT_Y, "ep": Feature.EXIT_P, "eg": Feature.EXIT_G, "eo": Feature.EXIT_O,
    "vy": Feature.VORTEX_Y, "vp": Feature.VORTEX_P, "vg": Feature.VORTEX_G, "vo": Feature.VORTEX_O,
    "xy": Feature.EXPLORE_Y, "xp": Feature.EXPLORE_P, "xg": Feature.EXPLORE_G, "xo": Feature.EXPLORE_O,
    "st": Feature.START,
    "t": Feature.SAND_TIMER,
    "c": Feature.CRYSTAL_BALL,
    "cam": Feature.CAMERA,
    "dp": Feature.DWARF_PASSAGE,
}

_VORTEX_TO_COLOR = {
    Feature.VORTEX_Y: Color.YELLOW,
    Feature.VORTEX_P: Color.PURPLE,
    Feature.VORTEX_G: Color.GREEN,
    Feature.VORTEX_O: Color.ORANGE,
}

_EXPLORE_TO_COLOR = {
    Feature.EXPLORE_Y: Color.YELLOW,
    Feature.EXPLORE_P: Color.PURPLE,
    Feature.EXPLORE_G: Color.GREEN,
    Feature.EXPLORE_O: Color.ORANGE,
}


def parse_cell(spec: str, escalator_to: tuple[int, int] | None = None,
               explore_edge: Direction | None = None) -> TileCellDef:
    walls_part, _, feat_part = spec.partition(":")
    if len(walls_part) != 4:
        raise ValueError(f"Cell wall spec must be 4 chars, got {spec!r}")
    walls: set[Direction] = set()
    for i, ch in enumerate(walls_part):
        if ch == "#":
            walls.add(WALL_CHARS_ORDER[i])
        elif ch != ".":
            raise ValueError(f"Bad wall char {ch!r} in {spec!r}")
    feats: list[Feature] = []
    vortex_color: Color | None = None
    explore_color: Color | None = None
    if feat_part:
        for code in feat_part.split(","):
            code = code.strip()
            if not code:
                continue
            if code not in _FEATURE_CODE_MAP:
                raise ValueError(f"Unknown feature code {code!r} in cell {spec!r}")
            f = _FEATURE_CODE_MAP[code]
            feats.append(f)
            if f in _VORTEX_TO_COLOR:
                vortex_color = _VORTEX_TO_COLOR[f]
            if f in _EXPLORE_TO_COLOR:
                explore_color = _EXPLORE_TO_COLOR[f]
    return TileCellDef(
        walls=frozenset(walls),
        features=tuple(feats),
        escalator_to=escalator_to,
        vortex_color=vortex_color,
        explore_color=explore_color,
        explore_edge=explore_edge,
    )


def load_tile(raw: dict) -> TileDef:
    cells_raw = raw["cells"]
    if len(cells_raw) != 4 or any(len(row) != 4 for row in cells_raw):
        raise ValueError(f"Tile {raw.get('id')} must be 4x4")

    escalator_pairs = raw.get("escalators", [])
    escalator_map: dict[tuple[int, int], tuple[int, int]] = {}
    for pair in escalator_pairs:
        (r1, c1), (r2, c2) = pair
        escalator_map[(r1, c1)] = (r2, c2)
        escalator_map[(r2, c2)] = (r1, c1)

    edges = raw.get("edges", {})
    explore_edge_map: dict[tuple[int, int], Direction] = {}
    for edge_name, anchors in edges.items():
        edge = Direction[edge_name]
        for anchor in anchors:
            if "at_row" in anchor:
                explore_edge_map[(anchor["at_row"], anchor.get("col", 0))] = edge
            if "col" in anchor and "at_row" not in anchor:
                row = 0 if edge == Direction.N else 3 if edge == Direction.S else None
                if row is None:
                    row = anchor.get("row", 0)
                explore_edge_map[(row, anchor["col"])] = edge

    cells: list[list[TileCellDef]] = []
    for r in range(4):
        row_cells: list[TileCellDef] = []
        for c in range(4):
            cell = parse_cell(
                cells_raw[r][c],
                escalator_to=escalator_map.get((r, c)),
                explore_edge=explore_edge_map.get((r, c)),
            )
            row_cells.append(cell)
        cells.append(row_cells)

    cells = _normalize_walls(cells, explore_edge_map)

    _validate_escalators_isolate(raw["id"], cells, escalator_map)

    return TileDef(
        id=raw["id"],
        cells=tuple(tuple(row) for row in cells),
        is_starting=raw.get("is_starting", False),
    )


def _validate_escalators_isolate(
    tile_id: str,
    cells: list[list[TileCellDef]],
    escalator_map: dict[tuple[int, int], tuple[int, int]],
) -> None:
    """Each escalator pair must link two cells that are in DIFFERENT connected
    components when the escalator itself is removed. (If the two cells are
    already reachable from each other by walking, the escalator is redundant.)
    """
    if not escalator_map:
        return

    def walk_neighbors(pos: tuple[int, int]):
        r, c = pos
        cell = cells[r][c]
        out: list[tuple[int, int]] = []
        if Direction.N not in cell.walls and r > 0:
            out.append((r - 1, c))
        if Direction.E not in cell.walls and c < 3:
            out.append((r, c + 1))
        if Direction.S not in cell.walls and r < 3:
            out.append((r + 1, c))
        if Direction.W not in cell.walls and c > 0:
            out.append((r, c - 1))
        return out

    seen_pairs: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for a, b in escalator_map.items():
        pair = (a, b) if a < b else (b, a)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        # BFS from a, NOT crossing the escalator link.
        reached: set[tuple[int, int]] = {a}
        stack = [a]
        while stack:
            cur = stack.pop()
            for nbr in walk_neighbors(cur):
                if nbr in reached:
                    continue
                reached.add(nbr)
                stack.append(nbr)
        if b in reached:
            raise ValueError(
                f"Tile {tile_id}: escalator {a}<->{b} is redundant — both "
                f"endpoints are already reachable from each other by walking. "
                f"Escalators must connect cells in separate connected components."
            )


def _normalize_walls(
    cells: list[list[TileCellDef]],
    explore_edge_map: dict[tuple[int, int], Direction],
) -> list[list[TileCellDef]]:
    """Make walls symmetric: if either side of a pair declares a wall, both sides
    get a wall. Also force the outer wall OPEN on cells that are explore doors
    (so the door is actually a passage). Outer (board-edge) walls that are not
    explore doors are forced CLOSED so the perimeter is consistent.
    """
    walls = [[set(cells[r][c].walls) for c in range(4)] for r in range(4)]

    for r in range(4):
        for c in range(4):
            # East/west pair
            if c < 3:
                if Direction.E in walls[r][c] or Direction.W in walls[r][c + 1]:
                    walls[r][c].add(Direction.E)
                    walls[r][c + 1].add(Direction.W)
            # North/south pair
            if r < 3:
                if Direction.S in walls[r][c] or Direction.N in walls[r + 1][c]:
                    walls[r][c].add(Direction.S)
                    walls[r + 1][c].add(Direction.N)

    # Perimeter: cells on the outer edge default to walled on that edge unless
    # they are an explore door (which means an opening to the next tile).
    for c in range(4):
        if explore_edge_map.get((0, c)) == Direction.N:
            walls[0][c].discard(Direction.N)
        else:
            walls[0][c].add(Direction.N)
        if explore_edge_map.get((3, c)) == Direction.S:
            walls[3][c].discard(Direction.S)
        else:
            walls[3][c].add(Direction.S)
    for r in range(4):
        if explore_edge_map.get((r, 0)) == Direction.W:
            walls[r][0].discard(Direction.W)
        else:
            walls[r][0].add(Direction.W)
        if explore_edge_map.get((r, 3)) == Direction.E:
            walls[r][3].discard(Direction.E)
        else:
            walls[r][3].add(Direction.E)

    out: list[list[TileCellDef]] = []
    for r in range(4):
        row: list[TileCellDef] = []
        for c in range(4):
            cur = cells[r][c]
            row.append(TileCellDef(
                walls=frozenset(walls[r][c]),
                one_way_forbidden=cur.one_way_forbidden,
                features=cur.features,
                escalator_to=cur.escalator_to,
                vortex_color=cur.vortex_color,
                explore_color=cur.explore_color,
                explore_edge=cur.explore_edge,
            ))
        out.append(row)
    return out


def load_tiles_from_file(path: str | Path) -> dict[str, TileDef]:
    with open(path, "r") as f:
        data = json.load(f)
    tiles = {}
    for raw in data["tiles"]:
        tile = load_tile(raw)
        tiles[tile.id] = tile
    return tiles
