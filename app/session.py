import uuid

from flask import session


def get_or_create_player_id() -> str:
    if "player_id" not in session:
        session["player_id"] = uuid.uuid4().hex
    return session["player_id"]


def get_username() -> str:
    return session.get("username", "Anonymous")


def set_username(name: str) -> None:
    session["username"] = name.strip()[:32] or "Anonymous"
