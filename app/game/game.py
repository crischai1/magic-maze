"""Game: central orchestration. Owns board, pawns, timer, phase, deltas."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Optional

from app.game.action_tiles import distribute as distribute_action_tiles
from app.game.board import Board, rotate_direction
from app.game.deltas import (
    CloseChatOp,
    DeltaOp,
    EndGameOp,
    ExplorationDoneOp,
    FlipPawnOp,
    MovePawnOp,
    OpenChatOp,
    PawnExitOp,
    PhaseChangeOp,
    PlaceTileOp,
    RequireExplorationOp,
    TimerFlipOp,
    UseCrystalBallOp,
    UseSandTimerOp,
)
from app.game.enums import (
    DIR_VECTOR,
    Color,
    Direction,
    Feature,
    Outcome,
    Phase,
)
from app.game.models import Pawn, Player, ScenarioConfig, TileDef
from app.game.move_validator import (
    Accept,
    MoveResult,
    Reject,
    check_exit_trigger,
    check_theft_trigger,
    validate_move,
)


def now_ms() -> int:
    return int(time.monotonic() * 1000)


@dataclass
class PendingExploration:
    player_id: str
    anchor_pos: tuple[int, int]
    anchor_edge: Direction
    remaining: int = 1  # how many tiles may still be placed (Crystal Ball grants 2)


class Game:
    def __init__(
        self,
        code: str,
        scenario: ScenarioConfig,
        players: list[Player],
        tile_registry: dict[str, TileDef],
        seed: Optional[int] = None,
    ):
        from app.game.timer import SandTimer

        self.code = code
        self.scenario = scenario
        self.players = players
        self.tile_registry = tile_registry
        self.board = Board(tile_registry)
        self.timer = SandTimer(scenario.starting_timer_ms)
        self.phase: Phase = Phase.WAITING
        self.pawns: dict[Color, Pawn] = {}
        self.deck: list[str] = list(scenario.deck_tile_ids)
        self.used_sand_timers: set[tuple[int, int]] = set()
        self.used_crystal_balls: set[tuple[int, int]] = set()
        self.disabled_cameras: set[tuple[int, int]] = set()
        self.chat_unlocked_until: Optional[int] = None
        # When the Mage steps on a Crystal Ball, this flag flips True. The NEXT
        # exploration (anyone, anywhere) consumes the flag and gets 2 tiles
        # instead of 1. Matches the original Magic Maze rule — the Crystal Ball
        # doesn't have to be on the Mage's own explore-anchor cell.
        self.pending_crystal_ball: bool = False
        self.pending_exploration: Optional[PendingExploration] = None
        self.outcome: Optional[Outcome] = None
        self.outcome_reason: str = ""
        self.version: int = 0
        self._seed = seed

    # ------- Lifecycle -------

    def start(self) -> list[DeltaOp]:
        self.board.place(self.scenario.start_tile, origin=(0, 0), rotation=0)
        # Per rules: place 4 hero pawns RANDOMLY on the 4 START squares.
        start_cells = self.board.find_feature(Feature.START)
        if len(start_cells) < 4:
            raise ValueError(
                f"Starting tile must have 4 START squares, found {len(start_cells)}"
            )
        rng = random.Random(self._seed)
        chosen = rng.sample(start_cells, 4)
        colors = list(Color)
        rng.shuffle(colors)
        for color, pos in zip(colors, chosen):
            self.pawns[color] = Pawn(color=color, pos=pos)
        # Shuffle deck per scenario
        rng.shuffle(self.deck)
        # Distribute action cards
        distribution = distribute_action_tiles([p.player_id for p in self.players], seed=self._seed)
        for player in self.players:
            player.action_tile = distribution.get(player.player_id)
        self.phase = Phase.EXPLORING
        return []

    def player_by_id(self, pid: str) -> Optional[Player]:
        for p in self.players:
            if p.player_id == pid:
                return p
        return None

    # ------- Move handling -------

    def apply_move(self, player: Player, pawn_color: Color, direction, target=None) -> MoveResult:
        result = validate_move(self, player, pawn_color, direction, target=target)
        if isinstance(result, Reject):
            return result
        for op in result.ops:
            self._apply_op(op)
        # Close any active chat window — any action ends the communication phase
        if self.chat_unlocked_until is not None:
            self.chat_unlocked_until = None
            result.ops.append(CloseChatOp())
        # Stealing trigger: all 4 heroes simultaneously on item squares
        theft_ops = check_theft_trigger(self)
        for op in theft_ops:
            self._apply_op(op)
        result.ops.extend(theft_ops)
        # Exit trigger for the moved pawn
        exit_ops = check_exit_trigger(self, pawn_color)
        for op in exit_ops:
            self._apply_op(op)
        result.ops.extend(exit_ops)
        # Win check
        end_ops = self._check_end()
        result.ops.extend(end_ops)
        for op in end_ops:
            self._apply_op(op)
        self.version += 1
        return result

    def _apply_op(self, op: DeltaOp) -> None:
        if isinstance(op, MovePawnOp):
            color = Color(op.color)
            self.pawns[color].pos = tuple(op.to_pos)
        elif isinstance(op, FlipPawnOp):
            color = Color(op.color)
            self.pawns[color].has_item = op.has_item
        elif isinstance(op, PawnExitOp):
            color = Color(op.color)
            self.pawns[color].exited = True
        elif isinstance(op, TimerFlipOp):
            # Per rules: the sand timer is literally flipped — the elapsed sand
            # becomes the new remaining. This can give you more or less time.
            self.timer.flip()
        elif isinstance(op, UseSandTimerOp):
            self.used_sand_timers.add(tuple(op.pos))
        elif isinstance(op, UseCrystalBallOp):
            self.used_crystal_balls.add(tuple(op.pos))
            # The next exploration (whether triggered manually via X or
            # auto-triggered by walking onto an anchor) will place 2 tiles
            # instead of 1. Consumed when a RequireExplorationOp fires.
            self.pending_crystal_ball = True
        elif isinstance(op, OpenChatOp):
            self.chat_unlocked_until = now_ms() + op.expires_at_ms
        elif isinstance(op, CloseChatOp):
            self.chat_unlocked_until = None
        elif isinstance(op, RequireExplorationOp):
            # If this exploration was upgraded to 2 tiles by a Crystal Ball,
            # consume the flag so the next exploration is back to 1 tile.
            if op.extra_tiles > 1:
                self.pending_crystal_ball = False
            self.pending_exploration = PendingExploration(
                player_id=op.player_id,
                anchor_pos=tuple(op.anchor_pos),
                anchor_edge=self._find_anchor_edge(tuple(op.anchor_pos)),
                remaining=op.extra_tiles,
            )
        elif isinstance(op, ExplorationDoneOp):
            self.pending_exploration = None
        elif isinstance(op, PhaseChangeOp):
            self.phase = Phase(op.new_phase)
        elif isinstance(op, PlaceTileOp):
            # No-op here; placement happens explicitly in commit_exploration.
            pass
        elif isinstance(op, EndGameOp):
            self.phase = Phase.FINISHED
            self.outcome = Outcome(op.outcome) if op.outcome else None
            self.outcome_reason = op.reason

    def _find_anchor_edge(self, pos: tuple[int, int]) -> Direction:
        cell = self.board.cell_at(pos)
        if cell is None or cell.explore_edge is None:
            for d in Direction:
                if self.board.neighbor(pos, d) is None:
                    return d
            return Direction.N
        return cell.explore_edge

    def _check_end(self) -> list[DeltaOp]:
        if self.phase == Phase.ESCAPING and all(p.exited for p in self.pawns.values()):
            self.phase = Phase.FINISHED
            self.outcome = Outcome.WIN
            self.outcome_reason = "All heroes escaped with the loot!"
            return [EndGameOp(outcome=Outcome.WIN.value, reason=self.outcome_reason)]
        return []

    # ------- Exploration -------

    def begin_exploration(self, player: Player, pawn_color: Color) -> MoveResult:
        if player.action_tile is None or self._action_explore() not in player.action_tile.actions:
            return Reject("your card doesn't permit explore")
        pawn = self.pawns.get(pawn_color)
        if pawn is None:
            return Reject("no such pawn")
        cell = self.board.cell_at(pawn.pos)
        if cell is None or cell.explore_color != pawn_color:
            return Reject("not standing on a matching explore anchor")
        if tuple(pawn.pos) in cell.tile.explored_anchors:
            return Reject("this anchor was already explored")
        if not self.deck:
            return Reject("no tiles remaining in the deck")
        # Crystal Ball: if the Mage previously activated one, the NEXT
        # exploration (this one) places 2 tiles instead of 1. The activation
        # happens when the Mage steps onto a Crystal Ball cell — see
        # validate_move + _apply_op(UseCrystalBallOp).
        extra = 2 if self.pending_crystal_ball else 1
        op = RequireExplorationOp(
            player_id=player.player_id, anchor_pos=tuple(pawn.pos), extra_tiles=extra
        )
        self._apply_op(op)
        self.version += 1
        return Accept([op])

    def _action_explore(self):
        from app.game.enums import ActionType

        return ActionType.EXPLORE

    def commit_exploration(self, player: Player) -> MoveResult:
        if self.pending_exploration is None:
            return Reject("no exploration pending")
        if self.pending_exploration.player_id != player.player_id:
            return Reject("only the triggering player can place the tile")
        if not self.deck:
            return Reject("deck empty")
        anchor_pos = self.pending_exploration.anchor_pos
        anchor_edge = self.pending_exploration.anchor_edge
        dr, dc = DIR_VECTOR[anchor_edge]
        adj = (anchor_pos[0] + dr, anchor_pos[1] + dc)
        if self.board.has_cell(adj):
            # Adjacent cell is already part of another tile — no new tile to
            # place. Consume the source anchor and the (existing) entrance cell.
            src_tile = self.board.cell_at(anchor_pos).tile
            src_tile.explored_anchors.add(tuple(anchor_pos))
            adj_tile = self.board.cell_at(adj).tile
            adj_tile.explored_anchors.add(tuple(adj))
            done = ExplorationDoneOp(
                sealed_anchors=[list(anchor_pos), list(adj)],
            )
            self._apply_op(done)
            self.version += 1
            return Accept([done])
        entrance_dir = anchor_edge.opposite()
        # Find the first deck tile that actually fits at this anchor — some
        # corridor tiles (with limited door positions) can be geometrically
        # unplaceable next to certain existing tiles.
        picked_idx = -1
        rotation: int = 0
        new_origin: tuple[int, int] = (0, 0)
        for idx, candidate_id in enumerate(self.deck):
            candidate = self.tile_registry[candidate_id]
            placement = self._compute_placement(
                candidate, adj, entrance_dir, anchor_pos, anchor_edge
            )
            if placement is not None:
                rotation, new_origin, _ = placement
                picked_idx = idx
                break
        if picked_idx < 0:
            # No tile in the deck fits here — seal the anchor as a dead end.
            src_tile = self.board.cell_at(anchor_pos).tile
            src_tile.explored_anchors.add(tuple(anchor_pos))
            done = ExplorationDoneOp(sealed_anchors=[list(anchor_pos)])
            self._apply_op(done)
            self.version += 1
            return Accept([done])
        new_tile_id = self.deck.pop(picked_idx)
        self.board.place(new_tile_id, new_origin, rotation)
        # Mark both doors as used: source (on previous tile) and entrance (on
        # newly placed tile). The hero walked through both, so both glyphs
        # should disappear and the passage is now open both ways.
        src_tile = self.board.cell_at(anchor_pos).tile
        src_tile.explored_anchors.add(tuple(anchor_pos))
        new_tile_placed = self.board.cell_at(adj).tile
        new_tile_placed.explored_anchors.add(tuple(adj))
        # Also: any OTHER doors on this newly-placed tile (or on existing
        # tiles) that now happen to face an occupied cell are dead — the
        # passage already exists, no new tile would be revealed by re-exploring.
        # Mark them explored so the door glyph disappears.
        # Snapshot the explored_anchors sets BEFORE the bulk-seal so we can
        # compute exactly which extra positions were added (and must be sent
        # to clients — the primary two are already in explored_anchor /
        # entrance_anchor on the PlaceTileOp).
        before_seal: dict[int, set] = {id(p): set(p.explored_anchors) for p in self.board.placed}
        self._seal_doors_facing_placed_tiles()
        extra_sealed = [
            list(a)
            for p in self.board.placed
            for a in p.explored_anchors
            if a not in before_seal.get(id(p), set())
        ]
        ops: list[DeltaOp] = [
            PlaceTileOp(
                tile_id=new_tile_id,
                origin=tuple(new_origin),
                rotation=rotation,
                explored_anchor=tuple(anchor_pos),
                entrance_anchor=tuple(adj),
                sealed_anchors=extra_sealed if extra_sealed else None,
            ),
        ]
        # Crystal Ball: if remaining > 1, keep the exploration alive for a second tile.
        self.pending_exploration.remaining -= 1
        if self.pending_exploration.remaining <= 0:
            ops.append(ExplorationDoneOp())
            for op in ops:
                self._apply_op(op)
        # Scenario 4+: when the Elf explores, unlock communication.
        if (
            "elf_explore_talks" in self.scenario.extra_rules
            and self.board.cell_at(anchor_pos).explore_color == Color.GREEN
        ):
            ops.append(OpenChatOp(expires_at_ms=self.scenario.do_anything_window_ms))
            self._apply_op(ops[-1])
        self.version += 1
        return Accept(ops)

    def _compute_placement(
        self,
        tile: TileDef,
        adj: tuple[int, int],
        entrance_dir: Direction,
        anchor_pos: tuple[int, int],
        anchor_edge: Direction,
    ) -> tuple[int, tuple[int, int], tuple[int, int]] | None:
        """Find a (rotation, origin, adj) that places `tile` so one of its
        explore-door cells lands at `adj` facing `entrance_dir` and the tile
        footprint does not overlap any existing tile. Returns None if no
        rotation fits — caller must handle (try a different tile or seal the
        anchor)."""
        for rotation in range(4):
            for lr in range(4):
                for lc in range(4):
                    cell_def = tile.cells[lr][lc]
                    if cell_def.explore_edge is None:
                        continue
                    if rotate_direction(cell_def.explore_edge, rotation) != entrance_dir:
                        continue
                    grow, gcol = self._rotate_local(lr, lc, rotation)
                    origin = (adj[0] - grow, adj[1] - gcol)
                    if self._overlap_free(origin):
                        return rotation, origin, adj
        return None

    def _rotate_local(self, lr: int, lc: int, rotation: int) -> tuple[int, int]:
        from app.game.board import rotate_local

        return rotate_local(lr, lc, rotation)

    def _overlap_free(self, origin: tuple[int, int]) -> bool:
        for r in range(4):
            for c in range(4):
                if (origin[0] + r, origin[1] + c) in self.board.cell_to_tile:
                    return False
        return True

    def _seal_doors_facing_placed_tiles(self) -> None:
        """For every placed tile, any explore-door cell whose outward neighbor
        is already part of another tile is functionally dead — the passage
        exists, but no further tile can be placed in that direction. Mark the
        door anchor as explored so the renderer hides the arrow glyph and the
        auto-trigger no longer fires on it.
        """
        for placed in self.board.placed:
            for r in range(4):
                for c in range(4):
                    pos = (placed.origin[0] + r, placed.origin[1] + c)
                    cell = self.board.cell_at(pos)
                    if cell is None or cell.explore_edge is None:
                        continue
                    dr, dc = DIR_VECTOR[cell.explore_edge]
                    neighbor_pos = (pos[0] + dr, pos[1] + dc)
                    if self.board.has_cell(neighbor_pos):
                        placed.explored_anchors.add(pos)

    # ------- Timer tick -------

    def tick(self, elapsed_ms: int) -> list[DeltaOp]:
        ops: list[DeltaOp] = []
        if self.phase not in (Phase.EXPLORING, Phase.ESCAPING):
            return ops
        self.timer.tick(elapsed_ms)
        # Communication window naturally expires (per rules it ends when any
        # action is taken; this is a UI safeguard).
        if self.chat_unlocked_until is not None and now_ms() >= self.chat_unlocked_until:
            self.chat_unlocked_until = None
            ops.append(CloseChatOp())
        if self.timer.expired and self.phase != Phase.FINISHED:
            self.phase = Phase.FINISHED
            self.outcome = Outcome.LOSS_TIME
            self.outcome_reason = "The mall security guards caught you!"
            ops.append(EndGameOp(outcome=Outcome.LOSS_TIME.value, reason=self.outcome_reason))
        if ops:
            self.version += 1
        return ops

    # ------- Chat -------

    def chat_unlocked(self) -> bool:
        return self.chat_unlocked_until is not None and now_ms() < self.chat_unlocked_until

    # ------- Snapshot -------

    def snapshot(self) -> dict:
        return {
            "code": self.code,
            "scenario": {
                "id": self.scenario.id,
                "name": self.scenario.name,
                "description": self.scenario.description,
                "starting_timer_ms": self.scenario.starting_timer_ms,
                "enabled_features": sorted(self.scenario.enabled_features),
                "extra_rules": list(self.scenario.extra_rules),
                "deck_total": len(self.scenario.deck_tile_ids),
                "colored_exits": self.scenario.colored_exits,
            },
            "phase": self.phase.value,
            "version": self.version,
            "timer": {"remaining_ms": self.timer.remaining_ms, "paused": self.timer.paused},
            "board": {
                "tiles": self.board.to_dict(),
                "tile_defs": self._tile_defs_for_placed(),
            },
            "pawns": {
                color.value: {"pos": list(pawn.pos), "has_item": pawn.has_item, "exited": pawn.exited}
                for color, pawn in self.pawns.items()
            },
            "players": [
                {
                    "player_id": p.player_id,
                    "username": p.username,
                    "is_host": p.is_host,
                    "connected": p.connected,
                    "actions": sorted(a.value for a in p.action_tile.actions) if p.action_tile else [],
                }
                for p in self.players
            ],
            "chat_unlocked": self.chat_unlocked(),
            "chat_unlocked_until": self.chat_unlocked_until,
            "used_sand_timers": [list(p) for p in self.used_sand_timers],
            "used_crystal_balls": [list(p) for p in self.used_crystal_balls],
            "pending_crystal_ball": self.pending_crystal_ball,
            "disabled_cameras": [list(p) for p in self.disabled_cameras],
            "pending_exploration": (
                {
                    "player_id": self.pending_exploration.player_id,
                    "anchor_pos": list(self.pending_exploration.anchor_pos),
                    "remaining": self.pending_exploration.remaining,
                    "next_tile_id": self.deck[0] if self.deck else None,
                }
                if self.pending_exploration
                else None
            ),
            "deck_remaining": len(self.deck),
            "outcome": self.outcome.value if self.outcome else None,
            "outcome_reason": self.outcome_reason,
        }

    def _tile_defs_for_placed(self) -> dict[str, dict]:
        defs: dict[str, dict] = {}
        for placed in self.board.placed:
            tile = self.tile_registry[placed.tile_id]
            if tile.id in defs:
                continue
            cells = []
            for r in range(4):
                row = []
                for c in range(4):
                    cell_def = tile.cells[r][c]
                    row.append({
                        # Direction.name = "N"/"E"/"S"/"W" — client expects strings.
                        # Direction.value is the int, which would break the client lookup.
                        "walls": [d.name for d in cell_def.walls],
                        "features": [f.value for f in cell_def.features],
                        "escalator_to": list(cell_def.escalator_to) if cell_def.escalator_to else None,
                        "vortex_color": cell_def.vortex_color.value if cell_def.vortex_color else None,
                        "explore_color": cell_def.explore_color.value if cell_def.explore_color else None,
                        "explore_edge": cell_def.explore_edge.name if cell_def.explore_edge is not None else None,
                    })
                cells.append(row)
            defs[tile.id] = {"id": tile.id, "cells": cells}
        return defs

    # ------- Reachability for UI -------

    def reachable_in_direction(self, player_id: str, pawn_color: Color, direction: Direction) -> list[list[int]]:
        from app.game.move_validator import reachable_slide_targets

        if self.phase not in (Phase.EXPLORING, Phase.ESCAPING):
            return []
        pawn = self.pawns.get(pawn_color)
        if pawn is None or pawn.exited:
            return []
        return [list(p) for p in reachable_slide_targets(self, pawn.pos, direction)]
