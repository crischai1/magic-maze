"""Lobby and LobbyManager: room codes, player slots, host promotion."""
from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from typing import Optional

from app.game.game import Game
from app.game.models import Player, ScenarioConfig, TileDef

CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # base32-ish, no I/O/0/1
CODE_LEN = 4


@dataclass
class Lobby:
    code: str
    players: list[Player] = field(default_factory=list)
    scenario_id: int = 1
    game: Optional[Game] = None

    def add_player(self, player: Player) -> None:
        if not self.players:
            player.is_host = True
        self.players.append(player)

    def remove_player(self, player_id: str) -> Optional[Player]:
        for i, p in enumerate(self.players):
            if p.player_id == player_id:
                removed = self.players.pop(i)
                # Promote a new host if needed
                if removed.is_host and self.players:
                    self.players[0].is_host = True
                return removed
        return None

    def get_player(self, player_id: str) -> Optional[Player]:
        for p in self.players:
            if p.player_id == player_id:
                return p
        return None

    def host(self) -> Optional[Player]:
        for p in self.players:
            if p.is_host:
                return p
        return None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "scenario_id": self.scenario_id,
            "players": [
                {
                    "player_id": p.player_id,
                    "username": p.username,
                    "is_host": p.is_host,
                    "connected": p.connected,
                }
                for p in self.players
            ],
            "in_game": self.game is not None,
        }


class LobbyManager:
    def __init__(self) -> None:
        self.lobbies: dict[str, Lobby] = {}
        self.tile_registry: dict[str, TileDef] = {}
        self.scenarios: dict[int, ScenarioConfig] = {}

    def configure(self, tile_registry: dict[str, TileDef], scenarios: dict[int, ScenarioConfig]) -> None:
        self.tile_registry = tile_registry
        self.scenarios = scenarios

    def generate_code(self) -> str:
        rng = random.SystemRandom()
        for _ in range(20):
            code = "".join(rng.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
            if code not in self.lobbies:
                return code
        raise RuntimeError("Could not generate a unique lobby code")

    def create_lobby(self) -> Lobby:
        code = self.generate_code()
        lobby = Lobby(code=code)
        self.lobbies[code] = lobby
        return lobby

    def get(self, code: str) -> Optional[Lobby]:
        return self.lobbies.get(code.upper())

    def delete(self, code: str) -> None:
        self.lobbies.pop(code.upper(), None)

    def start_game(self, lobby: Lobby, seed: Optional[int] = None) -> Game:
        scenario = self.scenarios.get(lobby.scenario_id)
        if scenario is None:
            raise ValueError(f"Unknown scenario {lobby.scenario_id}")
        if not lobby.players:
            raise ValueError("No players in lobby")
        if len(lobby.players) > scenario.max_players:
            raise ValueError(f"Too many players for scenario {scenario.id}")
        game = Game(
            code=lobby.code,
            scenario=scenario,
            players=lobby.players,
            tile_registry=self.tile_registry,
            seed=seed,
        )
        game.start()
        lobby.game = game
        return game
