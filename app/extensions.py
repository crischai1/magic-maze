from flask_socketio import SocketIO

from app.game.lobby import LobbyManager

socketio = SocketIO(async_mode="eventlet", cors_allowed_origins="*")
lobby_manager = LobbyManager()
