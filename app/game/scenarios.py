from __future__ import annotations

import json
from pathlib import Path

from app.game.models import ScenarioConfig


def load_scenarios(path: str | Path) -> dict[int, ScenarioConfig]:
    with open(path, "r") as f:
        data = json.load(f)
    out: dict[int, ScenarioConfig] = {}
    for raw in data["scenarios"]:
        out[raw["id"]] = ScenarioConfig(
            id=raw["id"],
            name=raw["name"],
            description=raw.get("description", ""),
            start_tile=raw["start_tile"],
            deck_tile_ids=tuple(raw["deck_tile_ids"]),
            starting_timer_ms=raw["starting_timer_ms"],
            do_anything_window_ms=raw.get("do_anything_window_ms", 5000),
            do_anything_resets_timer=raw.get("do_anything_resets_timer", False),
            vortex_locks_on_item=raw.get("vortex_locks_on_item", True),
            flip_pawn_bonus_ms=raw.get("flip_pawn_bonus_ms", 0),
            enabled_features=frozenset(raw.get("enabled_features", [])),
            extra_rules=tuple(raw.get("extra_rules", [])),
            min_players=raw.get("min_players", 1),
            max_players=raw.get("max_players", 8),
        )
    return out
