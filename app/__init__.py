import os

from flask import Flask

from app.config import Config


def create_app(config_class: type = Config):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)

    from app.extensions import lobby_manager, socketio
    from app.game.scenarios import load_scenarios
    from app.game.tile_loader import load_tiles_from_file

    data_dir = app.config["DATA_DIR"]
    tiles = load_tiles_from_file(os.path.join(data_dir, "tiles.json"))
    scenarios = load_scenarios(os.path.join(data_dir, "scenarios.json"))
    lobby_manager.configure(tiles, scenarios)

    socketio.init_app(app)

    from app.lobby_routes import bp as lobby_bp

    app.register_blueprint(lobby_bp)

    from app import sockets  # noqa: F401  (registers event handlers)

    return app, socketio
