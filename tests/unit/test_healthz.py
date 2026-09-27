"""/healthz reports lobbies with a connected player, so deploys can wait them out."""

from app import create_app
from app.extensions import lobby_manager
from app.game.models import Player


def test_healthz_counts_only_lobbies_with_someone_connected():
    app, _ = create_app()
    client = app.test_client()
    lobby_manager.lobbies.clear()
    assert client.get("/healthz").get_json() == {"ok": True, "rooms": 0}

    live = lobby_manager.create_lobby()
    live.add_player(Player(player_id="a", username="A"))
    gone = lobby_manager.create_lobby()
    gone.add_player(Player(player_id="b", username="B", connected=False))
    lobby_manager.create_lobby()  # nobody ever joined

    assert client.get("/healthz").get_json() == {"ok": True, "rooms": 1}
    lobby_manager.lobbies.clear()
