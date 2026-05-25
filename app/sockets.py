"""SocketIO event handlers for the /game namespace."""
from __future__ import annotations

import time
from typing import Optional

from flask import request, session
from flask_socketio import emit, join_room, leave_room

from app.extensions import lobby_manager, socketio
from app.game.enums import ActionType, Color, Direction, action_for_direction
from app.game.game import Game
from app.game.lobby import Lobby
from app.game.models import Player
from app.game.move_validator import Accept, Reject

NAMESPACE = "/game"

# Track sid → (code, player_id) for cleanup on disconnect.
_sid_to_context: dict[str, tuple[str, str]] = {}
# Track which lobbies have a running game loop greenthread.
_game_loops: dict[str, bool] = {}
# Lobby code → grace deadline (ms-epoch). While active, disconnects DO NOT
# remove players from the lobby — used during the Play-Again page navigation
# so the host slot survives the brief socket churn.
_post_game_grace: dict[str, int] = {}


def _player_from_session() -> tuple[Optional[str], Optional[str]]:
    pid = session.get("player_id")
    name = session.get("username") or "Player"
    return pid, name


def _broadcast_lobby(lobby: Lobby) -> None:
    socketio.emit("lobby:state", lobby.to_dict(), to=lobby.code, namespace=NAMESPACE)


def _broadcast_delta(game: Game, ops_dicts: list[dict]) -> None:
    socketio.emit(
        "game:delta",
        {"prev_version": game.version - 1, "version": game.version, "ops": ops_dicts},
        to=game.code,
        namespace=NAMESPACE,
    )


def _broadcast_snapshot(game: Game) -> None:
    socketio.emit("game:snapshot", game.snapshot(), to=game.code, namespace=NAMESPACE)


def _ops_to_dicts(ops, game: Game | None = None) -> list[dict]:
    out = []
    for op in ops:
        d = op.to_dict()
        # Newly placed tiles need their cell definitions sent so clients can render.
        if op.op == "place_tile" and game is not None:
            tile_def = game.tile_registry.get(op.tile_id)
            if tile_def is not None:
                d["tile_def"] = _serialize_tile_def(tile_def)
        out.append(d)
    return out


def _serialize_tile_def(tile_def) -> dict:
    cells = []
    for r in range(4):
        row = []
        for c in range(4):
            cell_def = tile_def.cells[r][c]
            row.append({
                # Direction.name = "N"/"E"/"S"/"W" — client expects strings.
                "walls": [d.name for d in cell_def.walls],
                "features": [f.value for f in cell_def.features],
                "escalator_to": list(cell_def.escalator_to) if cell_def.escalator_to else None,
                "vortex_color": cell_def.vortex_color.value if cell_def.vortex_color else None,
                "explore_color": cell_def.explore_color.value if cell_def.explore_color else None,
                "explore_edge": cell_def.explore_edge.name if cell_def.explore_edge is not None else None,
            })
        cells.append(row)
    return {"id": tile_def.id, "cells": cells}


# ----------------- Connection lifecycle -----------------


@socketio.on("connect", namespace=NAMESPACE)
def on_connect():
    pid, name = _player_from_session()
    if not pid:
        emit("error", {"message": "no session"})
        return False


@socketio.on("disconnect", namespace=NAMESPACE)
def on_disconnect():
    sid = request.sid
    context = _sid_to_context.pop(sid, None)
    if context is None:
        return
    code, pid = context
    lobby = lobby_manager.get(code)
    if lobby is None:
        return
    player = lobby.get_player(pid)
    if player is None:
        return
    player.connected = False
    player.sid = None
    now_ms = int(time.time() * 1000)
    in_post_game_grace = _post_game_grace.get(code, 0) > now_ms
    if lobby.game is None and not in_post_game_grace:
        # Pre-game: remove player from lobby
        lobby.remove_player(pid)
        _broadcast_lobby(lobby)
        if not lobby.players:
            lobby_manager.delete(code)
    elif lobby.game is None:
        # Post-game transition: keep their slot so the lobby survives the
        # Play-Again page navigation. They will reconnect via lobby:join.
        _broadcast_lobby(lobby)
    else:
        # In-game: keep their slot, broadcast state
        _broadcast_snapshot(lobby.game)


# ----------------- Lobby -----------------


@socketio.on("lobby:join", namespace=NAMESPACE)
def on_lobby_join(data):
    code = (data.get("code") or "").upper()
    username = (data.get("username") or "").strip()[:32] or "Player"
    pid, _ = _player_from_session()
    if not pid:
        emit("lobby:error", {"message": "no session"})
        return
    lobby = lobby_manager.get(code)
    if lobby is None:
        emit("lobby:error", {"message": f"no lobby {code}"})
        return

    join_room(code)
    _sid_to_context[request.sid] = (code, pid)

    existing = lobby.get_player(pid)
    if existing is not None:
        existing.sid = request.sid
        existing.connected = True
        existing.username = username
    else:
        if lobby.game is not None:
            emit("lobby:error", {"message": "game already in progress"})
            return
        player = Player(player_id=pid, username=username, sid=request.sid)
        lobby.add_player(player)

    _broadcast_lobby(lobby)
    if lobby.game is not None:
        # Send personalized snapshot to reconnecting player
        emit("game:snapshot", lobby.game.snapshot())


@socketio.on("lobby:leave", namespace=NAMESPACE)
def on_lobby_leave(data):
    code = (data.get("code") or "").upper()
    pid, _ = _player_from_session()
    lobby = lobby_manager.get(code)
    if lobby is None or pid is None:
        return
    leave_room(code)
    _sid_to_context.pop(request.sid, None)
    lobby.remove_player(pid)
    if not lobby.players:
        lobby_manager.delete(code)
    else:
        _broadcast_lobby(lobby)


@socketio.on("lobby:select_scenario", namespace=NAMESPACE)
def on_select_scenario(data):
    code = (data.get("code") or "").upper()
    sid_id = data.get("scenario_id")
    pid, _ = _player_from_session()
    lobby = lobby_manager.get(code)
    if lobby is None or pid is None:
        return
    player = lobby.get_player(pid)
    if player is None or not player.is_host:
        emit("lobby:error", {"message": "only the host can change scenario"})
        return
    if sid_id not in lobby_manager.scenarios:
        emit("lobby:error", {"message": "unknown scenario"})
        return
    lobby.scenario_id = sid_id
    _broadcast_lobby(lobby)


@socketio.on("lobby:start", namespace=NAMESPACE)
def on_lobby_start(data):
    code = (data.get("code") or "").upper()
    pid, _ = _player_from_session()
    lobby = lobby_manager.get(code)
    if lobby is None or pid is None:
        return
    player = lobby.get_player(pid)
    if player is None or not player.is_host:
        emit("lobby:error", {"message": "only the host can start the game"})
        return
    if lobby.game is not None:
        emit("lobby:error", {"message": "game already started"})
        return
    try:
        game = lobby_manager.start_game(lobby)
    except Exception as e:
        emit("lobby:error", {"message": str(e)})
        return
    _broadcast_lobby(lobby)
    _broadcast_snapshot(game)
    socketio.emit("lobby:redirect_to_game", {"code": code}, to=code, namespace=NAMESPACE)
    _ensure_game_loop(code)


# ----------------- Game actions -----------------


@socketio.on("game:move", namespace=NAMESPACE)
def on_move(data):
    code = (data.get("code") or "").upper()
    pawn_color = data.get("pawn_color")
    direction = data.get("direction")
    target = data.get("target")  # [row, col] — required for sliding & vortex
    pid, _ = _player_from_session()
    lobby = lobby_manager.get(code)
    if lobby is None or lobby.game is None or pid is None:
        return
    game = lobby.game
    player = game.player_by_id(pid)
    if player is None:
        emit("game:error", {"message": "player not in this game"})
        return
    try:
        color = Color(pawn_color)
    except ValueError:
        emit("game:error", {"message": "invalid pawn color"})
        return
    parsed: Direction | ActionType
    if direction in ("N", "E", "S", "W"):
        parsed = Direction[direction]
    elif direction == "ESCALATOR":
        parsed = ActionType.ESCALATOR
    elif direction == "VORTEX":
        parsed = ActionType.VORTEX
    else:
        emit("game:error", {"message": f"unknown direction {direction!r}"})
        return

    target_tuple = tuple(target) if target else None
    result = game.apply_move(player, color, parsed, target=target_tuple)
    if isinstance(result, Reject):
        emit("game:error", {"message": result.reason})
        return
    _broadcast_delta(game, _ops_to_dicts(result.ops, game))
    if game.phase.value == "finished":
        socketio.emit("game:result", {"outcome": game.outcome.value if game.outcome else None,
                                     "reason": game.outcome_reason},
                      to=game.code, namespace=NAMESPACE)


@socketio.on("game:reachable", namespace=NAMESPACE)
def on_reachable(data):
    """Client asks for legal slide destinations for a pawn in a direction.
    Sent on pawn select / hover so the UI can highlight the full slide range."""
    code = (data.get("code") or "").upper()
    pawn_color = data.get("pawn_color")
    pid, _ = _player_from_session()
    lobby = lobby_manager.get(code)
    if lobby is None or lobby.game is None or pid is None:
        return
    game = lobby.game
    try:
        color = Color(pawn_color)
    except ValueError:
        return
    player = game.player_by_id(pid)
    player_actions = player.action_tile.actions if (player and player.action_tile) else frozenset()
    out: dict[str, list[list[int]]] = {}
    for d in ("N", "E", "S", "W"):
        if action_for_direction(Direction[d]) not in player_actions:
            out[d] = []
            continue
        out[d] = game.reachable_in_direction(pid, color, Direction[d])
    # Vortex targets: only if player has VORTEX action
    pawn = game.pawns.get(color)
    vortex_targets: list[list[int]] = []
    if ActionType.VORTEX in player_actions and pawn is not None and not pawn.exited:
        for v in game.board.find_vortexes(color):
            if v == pawn.pos:
                continue
            occupied = any(p.pos == v and not p.exited for p in game.pawns.values())
            if occupied:
                continue
            vortex_targets.append(list(v))
    emit("game:reachable_result", {"pawn_color": pawn_color, "moves": out, "vortex": vortex_targets})


@socketio.on("game:explore", namespace=NAMESPACE)
def on_explore(data):
    code = (data.get("code") or "").upper()
    pawn_color = data.get("pawn_color")
    pid, _ = _player_from_session()
    lobby = lobby_manager.get(code)
    if lobby is None or lobby.game is None or pid is None:
        return
    game = lobby.game
    player = game.player_by_id(pid)
    if player is None:
        return
    try:
        color = Color(pawn_color)
    except ValueError:
        emit("game:error", {"message": "invalid pawn color"})
        return
    result = game.begin_exploration(player, color)
    if isinstance(result, Reject):
        emit("game:error", {"message": result.reason})
        return
    _broadcast_delta(game, _ops_to_dicts(result.ops, game))


@socketio.on("game:explore_commit", namespace=NAMESPACE)
def on_explore_commit(data):
    code = (data.get("code") or "").upper()
    pid, _ = _player_from_session()
    lobby = lobby_manager.get(code)
    if lobby is None or lobby.game is None or pid is None:
        return
    game = lobby.game
    player = game.player_by_id(pid)
    if player is None:
        return
    result = game.commit_exploration(player)
    if isinstance(result, Reject):
        emit("game:error", {"message": result.reason})
        return
    _broadcast_delta(game, _ops_to_dicts(result.ops, game))


@socketio.on("game:chat", namespace=NAMESPACE)
def on_chat(data):
    code = (data.get("code") or "").upper()
    text = (data.get("text") or "").strip()[:200]
    pid, _ = _player_from_session()
    lobby = lobby_manager.get(code)
    if lobby is None or lobby.game is None or pid is None or not text:
        return
    game = lobby.game
    if not game.chat_unlocked():
        emit("game:error", {"message": "chat is locked"})
        return
    player = game.player_by_id(pid)
    if player is None:
        return
    socketio.emit(
        "game:chat_message",
        {"from": pid, "username": player.username, "text": text, "ts": int(time.time() * 1000)},
        to=code,
        namespace=NAMESPACE,
    )


@socketio.on("game:request_resync", namespace=NAMESPACE)
def on_resync(data):
    code = (data.get("code") or "").upper()
    lobby = lobby_manager.get(code)
    if lobby is None or lobby.game is None:
        return
    emit("game:snapshot", lobby.game.snapshot())


@socketio.on("game:return_to_lobby", namespace=NAMESPACE)
def on_return_to_lobby(data):
    """Reset a finished game so the lobby can play again without a new share code."""
    code = (data.get("code") or "").upper()
    pid, _ = _player_from_session()
    lobby = lobby_manager.get(code)
    if lobby is None or pid is None:
        return
    if lobby.game is None or lobby.game.phase.value != "finished":
        return
    # Clear action tiles on lobby players so they are re-dealt next game.
    for player in lobby.players:
        player.action_tile = None
    lobby.game = None
    # Arm the disconnect-grace window so the page-navigation churn that follows
    # this event doesn't tear the lobby down.
    _post_game_grace[code] = int(time.time() * 1000) + 15000
    _broadcast_lobby(lobby)
    socketio.emit("lobby:redirect_to_lobby", {"code": code}, to=code, namespace=NAMESPACE)


# ----------------- Game loop greenthread -----------------


def _ensure_game_loop(code: str) -> None:
    if _game_loops.get(code):
        return
    _game_loops[code] = True
    socketio.start_background_task(_game_loop, code)


def _game_loop(code: str) -> None:
    import eventlet

    last = int(time.monotonic() * 1000)
    chat_open_announced = False
    while True:
        eventlet.sleep(0.2)
        lobby = lobby_manager.get(code)
        if lobby is None or lobby.game is None:
            break
        game = lobby.game
        if game.phase.value == "finished":
            socketio.emit(
                "game:tick",
                {"remaining_ms": game.timer.remaining_ms, "paused": True},
                to=code,
                namespace=NAMESPACE,
            )
            break
        now = int(time.monotonic() * 1000)
        elapsed = now - last
        last = now
        ops = game.tick(elapsed)
        if ops:
            _broadcast_delta(game, _ops_to_dicts(ops, game))
            if game.phase.value == "finished":
                socketio.emit(
                    "game:result",
                    {"outcome": game.outcome.value if game.outcome else None,
                     "reason": game.outcome_reason},
                    to=code,
                    namespace=NAMESPACE,
                )
        # Always send a thin timer tick at 5 Hz
        socketio.emit(
            "game:tick",
            {
                "remaining_ms": game.timer.remaining_ms,
                "paused": game.timer.paused,
                "chat_unlocked": game.chat_unlocked(),
                "chat_unlocked_until": game.chat_unlocked_until,
            },
            to=code,
            namespace=NAMESPACE,
        )
    _game_loops.pop(code, None)
