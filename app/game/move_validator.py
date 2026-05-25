"""Move validation: single source of truth for legal actions.

Magic Maze movement rules:
- A move action lets the player slide a hero any number of cells in the action's
  direction, stopping before a wall, another hero, or the board edge.
  The MOVING player chooses where to stop; the server accepts any cell in the
  legal range. (Rulebook: "you are never allowed to stop another player's
  movement: that player must decide when it is the appropriate time to stop.")
- Vortex: the player with the Use-Vortex card may teleport any hero from
  anywhere to any vortex space of the hero's own color. Disabled after theft.
- Escalator: from a cell with an escalator, jump to the paired endpoint.
- Stealing is not an action: it happens automatically when all 4 heroes are
  simultaneously standing on their matching Item spaces.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

from app.game.deltas import (
    DeltaOp,
    EndGameOp,
    FlipPawnOp,
    MovePawnOp,
    OpenChatOp,
    PawnExitOp,
    PhaseChangeOp,
    RequireExplorationOp,
    TimerFlipOp,
    UseCrystalBallOp,
    UseSandTimerOp,
)
from app.game.enums import (
    DIR_VECTOR,
    EXIT_FOR_COLOR,
    ITEM_FOR_COLOR,
    ActionType,
    Color,
    Direction,
    Feature,
    Phase,
    action_for_direction,
)
from app.game.models import Player

if TYPE_CHECKING:
    from app.game.game import Game


@dataclass
class Accept:
    ops: list[DeltaOp]


@dataclass
class Reject:
    reason: str


MoveResult = Union[Accept, Reject]


def _pawn_at(game: "Game", pos: tuple[int, int]) -> Color | None:
    for color, pawn in game.pawns.items():
        if pawn.exited:
            continue
        if pawn.pos == pos:
            return color
    return None


def reachable_slide_targets(game: "Game", from_pos: tuple[int, int], direction: Direction) -> list[tuple[int, int]]:
    """Return all cells reachable by sliding from `from_pos` in `direction`.

    A pawn may stop on any of these cells. Sliding stops *before* a wall, the
    board edge, or another (non-exited) hero.
    """
    results: list[tuple[int, int]] = []
    dr, dc = DIR_VECTOR[direction]
    cur = from_pos
    while True:
        ok, _ = game.board.can_traverse(cur, direction)
        if not ok:
            break
        nxt = (cur[0] + dr, cur[1] + dc)
        # Blocked by another hero
        if _pawn_at(game, nxt) is not None:
            break
        results.append(nxt)
        cur = nxt
    return results


def validate_move(game: "Game", player: Player, pawn_color: Color, direction: Direction | ActionType,
                  target: tuple[int, int] | None = None) -> MoveResult:
    if game.phase not in (Phase.EXPLORING, Phase.ESCAPING):
        return Reject("game not active")
    if game.timer.expired:
        return Reject("time's up")
    pawn = game.pawns.get(pawn_color)
    if pawn is None or pawn.exited:
        return Reject("invalid pawn")
    if player.action_tile is None:
        return Reject("you have no action card")

    # ---- Required action ----
    if isinstance(direction, Direction):
        required = action_for_direction(direction)
    elif direction == ActionType.ESCALATOR:
        required = ActionType.ESCALATOR
    elif direction == ActionType.VORTEX:
        required = ActionType.VORTEX
    elif direction == ActionType.EXPLORE:
        required = ActionType.EXPLORE
    else:
        return Reject(f"unknown direction {direction!r}")

    if required not in player.action_tile.actions:
        return Reject(f"your card doesn't permit {required.value}")

    cell = game.board.cell_at(pawn.pos)
    if cell is None:
        return Reject("pawn off board")

    # ---- Resolve destination ----
    if isinstance(direction, Direction):
        reachable = reachable_slide_targets(game, pawn.pos, direction)
        if not reachable:
            return Reject("nothing in that direction")
        if target is None:
            # Default: slide as far as possible
            new_pos = reachable[-1]
        else:
            t = tuple(target)
            if t not in reachable:
                return Reject("can't stop there in a straight slide")
            new_pos = t

    elif required == ActionType.ESCALATOR:
        if cell.escalator_to_global is None:
            return Reject("no escalator on this square")
        new_pos = cell.escalator_to_global
        if _pawn_at(game, new_pos) is not None:
            return Reject("escalator destination is occupied")

    elif required == ActionType.VORTEX:
        # Per rules: teleport ANY hero from anywhere to ANY vortex of the hero's color.
        # Disabled once theft has occurred.
        if game.scenario.vortex_locks_on_item and game.phase == Phase.ESCAPING:
            return Reject("vortexes are disabled after the theft")
        if "vortex" not in game.scenario.enabled_features:
            return Reject("vortexes are out of service")
        if target is None:
            return Reject("must pick a destination vortex")
        candidates = game.board.find_vortexes(pawn_color)
        if tuple(target) not in candidates:
            return Reject("destination is not a vortex of this hero's color")
        if tuple(target) == tuple(pawn.pos):
            return Reject("hero is already there")
        if _pawn_at(game, tuple(target)) is not None:
            return Reject("that vortex is occupied")
        new_pos = tuple(target)

    elif required == ActionType.EXPLORE:
        return Reject("use the explore flow instead")
    else:
        return Reject("unhandled action")

    target_cell = game.board.cell_at(new_pos)
    if target_cell is None:
        return Reject("target off board")

    # Scenario rule: 2+ active Security Cameras disable timer flips and we don't
    # need to block movement here — sand-timer-step handler will refuse the flip.

    ops: list[DeltaOp] = [
        MovePawnOp(color=pawn_color.value, from_pos=tuple(pawn.pos), to_pos=tuple(new_pos)),
    ]

    # ---- Sand Timer space (one-use): flip the timer, open chat window ----
    if Feature.SAND_TIMER in target_cell.features and tuple(new_pos) not in game.used_sand_timers:
        active_cams = _active_camera_count(game)
        if active_cams < 2:
            ops.append(UseSandTimerOp(pos=tuple(new_pos)))
            ops.append(TimerFlipOp())
            ops.append(OpenChatOp(expires_at_ms=game.scenario.do_anything_window_ms))

    # ---- Crystal Ball (Mage-only): grant a 2-tile explore privilege ----
    if (
        Feature.CRYSTAL_BALL in target_cell.features
        and pawn_color == Color.PURPLE
        and tuple(new_pos) not in game.used_crystal_balls
        and "crystal_ball" in game.scenario.enabled_features
    ):
        ops.append(UseCrystalBallOp(pos=tuple(new_pos)))

    # ---- Security Camera disable (Barbarian only) ----
    if (
        Feature.CAMERA in target_cell.features
        and pawn_color == Color.YELLOW
        and tuple(new_pos) not in game.disabled_cameras
        and "camera" in game.scenario.extra_rules
    ):
        ops.append(UseSandTimerOp(pos=tuple(new_pos)))  # reuse out-of-order semantics

    # ---- Exploration auto-trigger when matching pawn lands on explore anchor ----
    if (
        target_cell.explore_color == pawn_color
        and tuple(new_pos) not in target_cell.tile.explored_anchors
        and game.deck
    ):
        # Crystal Ball: extra_tiles=2 if a Crystal Ball is already armed OR if
        # this very move JUST armed one (UseCrystalBallOp earlier in ops).
        crystal_active = game.pending_crystal_ball or any(
            isinstance(o, UseCrystalBallOp) for o in ops
        )
        extra_tiles = 2 if crystal_active else 1
        ops.append(RequireExplorationOp(
            player_id=player.player_id,
            anchor_pos=tuple(new_pos),
            extra_tiles=extra_tiles,
        ))

    return Accept(ops)


def _active_camera_count(game: "Game") -> int:
    """How many security-camera squares are revealed and not yet disabled."""
    if "camera" not in game.scenario.extra_rules:
        return 0
    count = 0
    for cell in game.board.all_cells():
        if Feature.CAMERA in cell.features and tuple(cell.global_pos) not in game.disabled_cameras:
            count += 1
    return count


def check_theft_trigger(game: "Game") -> list[DeltaOp]:
    """If all 4 heroes are simultaneously on their Item spaces, the theft happens."""
    if game.phase != Phase.EXPLORING:
        return []
    for color, pawn in game.pawns.items():
        cell = game.board.cell_at(pawn.pos)
        if cell is None:
            return []
        if ITEM_FOR_COLOR[color] not in cell.features:
            return []
    # All heroes are on their item squares
    ops: list[DeltaOp] = []
    for color, pawn in game.pawns.items():
        if not pawn.has_item:
            ops.append(FlipPawnOp(color=color.value, has_item=True))
    ops.append(PhaseChangeOp(new_phase=Phase.ESCAPING.value))
    return ops


def check_exit_trigger(game: "Game", color: Color) -> list[DeltaOp]:
    """If a hero is on its matching exit during ESCAPING phase, mark it exited.

    When the scenario sets any_hero_can_exit=True, any hero may exit through
    any exit cell regardless of colour — used in Scenario 1 (single exit).
    """
    if game.phase != Phase.ESCAPING:
        return []
    pawn = game.pawns.get(color)
    if pawn is None or pawn.exited:
        return []
    cell = game.board.cell_at(pawn.pos)
    if cell is None:
        return []
    if EXIT_FOR_COLOR[color] in cell.features:
        return [PawnExitOp(color=color.value)]
    if game.scenario.any_hero_can_exit:
        all_exits = frozenset(EXIT_FOR_COLOR.values())
        if any(f in cell.features for f in all_exits):
            return [PawnExitOp(color=color.value)]
    return []
