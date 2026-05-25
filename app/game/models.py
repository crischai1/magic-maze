from dataclasses import dataclass, field
from typing import Optional, Set

from app.game.enums import ActionType, Color, Direction, Feature


@dataclass(frozen=True)
class TileCellDef:
    walls: frozenset[Direction] = frozenset()
    one_way_forbidden: tuple[Direction, ...] = ()
    features: tuple[Feature, ...] = ()
    escalator_to: Optional[tuple[int, int]] = None
    vortex_color: Optional[Color] = None
    explore_color: Optional[Color] = None
    explore_edge: Optional[Direction] = None


@dataclass(frozen=True)
class TileDef:
    id: str
    cells: tuple[tuple[TileCellDef, ...], ...]
    is_starting: bool = False


@dataclass
class PlacedTile:
    tile_id: str
    origin: tuple[int, int]
    rotation: int = 0
    # All door cells on this tile that have been "used" — the player walked
    # through them into/out of an adjacent tile. Once used, a door no longer
    # renders and never triggers exploration again. Stored as a set of global
    # cell coordinates so both the source door and the destination tile's
    # entrance door can be marked.
    explored_anchors: Set[tuple[int, int]] = field(default_factory=set)


@dataclass
class Pawn:
    color: Color
    pos: tuple[int, int]
    has_item: bool = False
    exited: bool = False


@dataclass(frozen=True)
class ActionTile:
    actions: frozenset[ActionType]


@dataclass
class Player:
    player_id: str
    username: str
    sid: Optional[str] = None
    is_host: bool = False
    action_tile: Optional[ActionTile] = None
    connected: bool = True


@dataclass(frozen=True)
class ScenarioConfig:
    id: int
    name: str
    description: str
    start_tile: str
    deck_tile_ids: tuple[str, ...]
    starting_timer_ms: int
    do_anything_window_ms: int = 5000
    do_anything_resets_timer: bool = False
    vortex_locks_on_item: bool = True
    flip_pawn_bonus_ms: int = 0
    enabled_features: frozenset[str] = field(default_factory=frozenset)
    extra_rules: tuple[str, ...] = ()
    min_players: int = 1
    max_players: int = 8
    colored_exits: bool = True
    any_hero_can_exit: bool = False


@dataclass
class ResolvedCell:
    """A tile cell resolved into global coordinates and rotation."""

    global_pos: tuple[int, int]
    tile: PlacedTile
    local_row: int
    local_col: int
    walls: frozenset[Direction]
    one_way_forbidden: tuple[Direction, ...]
    features: tuple[Feature, ...]
    escalator_to_global: Optional[tuple[int, int]] = None
    vortex_color: Optional[Color] = None
    explore_color: Optional[Color] = None
    explore_edge: Optional[Direction] = None
