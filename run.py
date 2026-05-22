import eventlet
eventlet.monkey_patch()

import os

from app import create_app

app, socketio = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(app, host="127.0.0.1", port=port, debug=debug)
