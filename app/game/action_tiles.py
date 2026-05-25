"""Distribute action cards to players based on player count.

In actual Magic Maze, the action set is split across players such that no one
person can perform every action. With fewer than 4 players, cards are merged.

Multiple partition options are defined per player count so players are unlikely
to receive the same card layout twice in a row.
"""
from __future__ import annotations

import random
from typing import Iterable

from app.game.enums import ActionType
from app.game.models import ActionTile

ALL_ACTIONS = frozenset(ActionType)

_N = ActionType.MOVE_N
_E = ActionType.MOVE_E
_S = ActionType.MOVE_S
_W = ActionType.MOVE_W
_ESC = ActionType.ESCALATOR
_VRT = ActionType.VORTEX
_EXP = ActionType.EXPLORE

# Each entry is a tuple of possible partitions for that player count.
# At game-start one partition is chosen randomly, then the cards within it
# are shuffled so each player is also unlikely to draw the same card.
_PARTITION_SETS: dict[int, tuple[tuple[frozenset[ActionType], ...], ...]] = {
    1: (
        (frozenset(ALL_ACTIONS),),
    ),
    2: (
        (frozenset({_N, _E, _ESC, _EXP}),  frozenset({_S, _W, _VRT})),
        (frozenset({_N, _S, _VRT, _EXP}),  frozenset({_E, _W, _ESC})),
        (frozenset({_N, _W, _ESC, _EXP}),  frozenset({_S, _E, _VRT})),
        (frozenset({_E, _S, _VRT, _EXP}),  frozenset({_N, _W, _ESC})),
        (frozenset({_S, _W, _ESC, _EXP}),  frozenset({_N, _E, _VRT})),
        (frozenset({_N, _E, _VRT}),         frozenset({_S, _W, _ESC, _EXP})),
    ),
    3: (
        (frozenset({_N, _W}),         frozenset({_S, _E}),        frozenset({_ESC, _VRT, _EXP})),
        (frozenset({_N, _E}),         frozenset({_S, _W}),        frozenset({_ESC, _VRT, _EXP})),
        (frozenset({_N, _S}),         frozenset({_E, _W}),        frozenset({_ESC, _VRT, _EXP})),
        (frozenset({_N, _ESC}),       frozenset({_E, _VRT}),      frozenset({_S, _W, _EXP})),
        (frozenset({_N, _VRT}),       frozenset({_S, _ESC}),      frozenset({_E, _W, _EXP})),
        (frozenset({_N, _EXP}),       frozenset({_E, _W}),        frozenset({_S, _VRT, _ESC})),
        (frozenset({_E, _ESC}),       frozenset({_W, _VRT}),      frozenset({_N, _S, _EXP})),
        (frozenset({_S, _EXP}),       frozenset({_N, _ESC}),      frozenset({_E, _W, _VRT})),
    ),
    4: (
        (frozenset({_N, _EXP}),       frozenset({_E, _ESC}),   frozenset({_S, _VRT}),  frozenset({_W})),
        (frozenset({_N, _W}),         frozenset({_E, _EXP}),   frozenset({_S, _ESC}),  frozenset({_VRT})),
        (frozenset({_N, _VRT}),       frozenset({_E, _W}),     frozenset({_S, _EXP}),  frozenset({_ESC})),
        (frozenset({_N, _ESC}),       frozenset({_E, _VRT}),   frozenset({_S, _W}),    frozenset({_EXP})),
        (frozenset({_N, _S}),         frozenset({_E, _W}),     frozenset({_ESC, _EXP}), frozenset({_VRT})),
        (frozenset({_N, _E, _VRT}),   frozenset({_S, _W}),     frozenset({_ESC}),      frozenset({_EXP})),
        (frozenset({_E, _S, _EXP}),   frozenset({_N, _W}),     frozenset({_VRT}),      frozenset({_ESC})),
        (frozenset({_W, _ESC}),        frozenset({_N, _VRT}),   frozenset({_E, _S}),    frozenset({_EXP})),
    ),
    5: (
        (frozenset({_N}), frozenset({_E}), frozenset({_S}), frozenset({_W}), frozenset({_ESC, _VRT, _EXP})),
        (frozenset({_N}), frozenset({_E}), frozenset({_S}), frozenset({_W, _VRT}), frozenset({_ESC, _EXP})),
        (frozenset({_N}), frozenset({_E}), frozenset({_S, _VRT}), frozenset({_W}), frozenset({_ESC, _EXP})),
        (frozenset({_N, _VRT}), frozenset({_E}), frozenset({_S}), frozenset({_W}), frozenset({_ESC, _EXP})),
        (frozenset({_N}), frozenset({_E, _EXP}), frozenset({_S}), frozenset({_W}), frozenset({_ESC, _VRT})),
        (frozenset({_N}), frozenset({_E}), frozenset({_S, _EXP}), frozenset({_W}), frozenset({_ESC, _VRT})),
    ),
    6: (
        (frozenset({_N}), frozenset({_E}), frozenset({_S}), frozenset({_W}), frozenset({_ESC, _EXP}), frozenset({_VRT})),
        (frozenset({_N}), frozenset({_E}), frozenset({_S}), frozenset({_W}), frozenset({_ESC}), frozenset({_VRT, _EXP})),
        (frozenset({_N}), frozenset({_E}), frozenset({_S}), frozenset({_W, _EXP}), frozenset({_ESC}), frozenset({_VRT})),
    ),
    7: (
        (frozenset({_N}), frozenset({_E}), frozenset({_S}), frozenset({_W}), frozenset({_ESC}), frozenset({_VRT}), frozenset({_EXP})),
    ),
    8: (
        (frozenset({_N}), frozenset({_E}), frozenset({_S}), frozenset({_W}), frozenset({_ESC}), frozenset({_VRT}), frozenset({_EXP}), frozenset({_N, _E})),
    ),
}


def distribute(player_ids: Iterable[str], seed: int | None = None) -> dict[str, ActionTile]:
    player_list = list(player_ids)
    n = len(player_list)
    if n < 1:
        return {}
    if n > 8:
        raise ValueError("max 8 players")
    rng = random.Random(seed) if seed is not None else random.Random()
    # Pick one partition layout at random, then shuffle the cards within it.
    partition_options = _PARTITION_SETS[n]
    chosen_partition = rng.choice(partition_options)
    cards = list(chosen_partition)
    rng.shuffle(cards)
    return {pid: ActionTile(actions=cards[i]) for i, pid in enumerate(player_list)}


def union_of_actions(distribution: dict[str, ActionTile]) -> frozenset[ActionType]:
    out: set[ActionType] = set()
    for tile in distribution.values():
        out.update(tile.actions)
    return frozenset(out)
