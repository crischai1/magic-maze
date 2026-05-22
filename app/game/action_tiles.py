"""Distribute action cards to players based on player count.

In actual Magic Maze, the action set is split across players such that no one
person can perform every action. With fewer than 4 players, cards are merged.
"""
from __future__ import annotations

import random
from typing import Iterable

from app.game.enums import ActionType
from app.game.models import ActionTile

ALL_ACTIONS = frozenset(ActionType)

_PARTITIONS: dict[int, tuple[frozenset[ActionType], ...]] = {
    1: (
        frozenset(ALL_ACTIONS),
    ),
    2: (
        frozenset({ActionType.MOVE_N, ActionType.MOVE_E, ActionType.ESCALATOR, ActionType.EXPLORE}),
        frozenset({ActionType.MOVE_S, ActionType.MOVE_W, ActionType.VORTEX, ActionType.EXPLORE}),
    ),
    3: (
        frozenset({ActionType.MOVE_N, ActionType.MOVE_W}),
        frozenset({ActionType.MOVE_S, ActionType.MOVE_E}),
        frozenset({ActionType.ESCALATOR, ActionType.VORTEX, ActionType.EXPLORE}),
    ),
    4: (
        frozenset({ActionType.MOVE_N, ActionType.EXPLORE}),
        frozenset({ActionType.MOVE_E, ActionType.ESCALATOR}),
        frozenset({ActionType.MOVE_S, ActionType.VORTEX}),
        frozenset({ActionType.MOVE_W}),
    ),
    5: (
        frozenset({ActionType.MOVE_N}),
        frozenset({ActionType.MOVE_E}),
        frozenset({ActionType.MOVE_S}),
        frozenset({ActionType.MOVE_W}),
        frozenset({ActionType.ESCALATOR, ActionType.VORTEX, ActionType.EXPLORE}),
    ),
    6: (
        frozenset({ActionType.MOVE_N}),
        frozenset({ActionType.MOVE_E}),
        frozenset({ActionType.MOVE_S}),
        frozenset({ActionType.MOVE_W}),
        frozenset({ActionType.ESCALATOR, ActionType.EXPLORE}),
        frozenset({ActionType.VORTEX}),
    ),
    7: (
        frozenset({ActionType.MOVE_N}),
        frozenset({ActionType.MOVE_E}),
        frozenset({ActionType.MOVE_S}),
        frozenset({ActionType.MOVE_W}),
        frozenset({ActionType.ESCALATOR}),
        frozenset({ActionType.VORTEX}),
        frozenset({ActionType.EXPLORE}),
    ),
    8: (
        frozenset({ActionType.MOVE_N}),
        frozenset({ActionType.MOVE_E}),
        frozenset({ActionType.MOVE_S}),
        frozenset({ActionType.MOVE_W}),
        frozenset({ActionType.ESCALATOR}),
        frozenset({ActionType.VORTEX}),
        frozenset({ActionType.EXPLORE}),
        frozenset({ActionType.MOVE_N, ActionType.MOVE_E}),  # bonus duplicate card
    ),
}


def distribute(player_ids: Iterable[str], seed: int | None = None) -> dict[str, ActionTile]:
    player_list = list(player_ids)
    n = len(player_list)
    if n < 1:
        return {}
    if n > 8:
        raise ValueError("max 8 players")
    cards = list(_PARTITIONS[n])
    rng = random.Random(seed) if seed is not None else random.Random()
    rng.shuffle(cards)
    return {pid: ActionTile(actions=cards[i]) for i, pid in enumerate(player_list)}


def union_of_actions(distribution: dict[str, ActionTile]) -> frozenset[ActionType]:
    out: set[ActionType] = set()
    for tile in distribution.values():
        out.update(tile.actions)
    return frozenset(out)
