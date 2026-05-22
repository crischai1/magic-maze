from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.extensions import lobby_manager
from app.session import get_or_create_player_id, get_username, set_username

bp = Blueprint("lobby", __name__)


@bp.before_app_request
def ensure_identity() -> None:
    get_or_create_player_id()


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if username:
            set_username(username)
        action = request.form.get("action")
        if action == "create":
            lobby = lobby_manager.create_lobby()
            return redirect(url_for("lobby.lobby_page", code=lobby.code))
        if action == "join":
            code = (request.form.get("code") or "").strip().upper()
            lobby = lobby_manager.get(code)
            if lobby is None:
                return render_template("index.html", error=f"No lobby {code!r}", username=get_username())
            return redirect(url_for("lobby.lobby_page", code=lobby.code))
    return render_template("index.html", username=get_username(), error=None)


@bp.route("/lobby/<code>")
def lobby_page(code: str):
    lobby = lobby_manager.get(code)
    if lobby is None:
        return render_template("index.html", error=f"Lobby {code!r} not found", username=get_username()), 404
    if lobby.game is not None and lobby.game.phase.value != "waiting":
        return redirect(url_for("lobby.game_page", code=code))
    scenarios = sorted(lobby_manager.scenarios.values(), key=lambda s: s.id)
    return render_template(
        "lobby.html",
        lobby=lobby,
        code=lobby.code,
        username=get_username(),
        player_id=get_or_create_player_id(),
        scenarios=scenarios,
    )


@bp.route("/game/<code>")
def game_page(code: str):
    lobby = lobby_manager.get(code)
    if lobby is None or lobby.game is None:
        abort(404)
    return render_template(
        "game.html",
        code=lobby.code,
        username=get_username(),
        player_id=get_or_create_player_id(),
    )
