#!/bin/env python

#   Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
#   All rights reserved.
#   This file is part of the Avalon-NLU repository,
#   and is released under the "MIT License Agreement". Please see the LICENSE
#   file that should have been included as part of this package.

import json
from flask import Flask
from hashids import Hashids
import time
from threading import Semaphore
from flask_htpasswd import HtPasswdAuth
from flask_socketio import SocketIO
import werkzeug
from src.clogin import VLogin
from src.cregister import VRegister
from src.clobby import VLobby
from src.cgame import NSGame, VGame
from src.manager import Manager
from flask_login import LoginManager
from src.user import User

def main():
    config = None
    with open("config.json", "r") as fh:
        config = json.load(fh)

    socketio = SocketIO()
    manager = Manager(config, socketio)

    app = Flask(__name__, template_folder="./templates")
    # app.wsgi_app = werkzeug.middleware.shared_data.SharedDataMiddleware(socketio, app.wsgi_app)
    app.config['FLASK_HTPASSWD_PATH'] = './templates/.htpasswd'
    app.config['FLASK_SECRET'] = config["flask"]["flask_secret"]
    # htpasswd = HtPasswdAuth(app)

    app.config['SECRET_KEY'] = config["flask"]["secret_key"]
    app.debug = config["server"]["debug"]

    login_manager = LoginManager()
    login_manager.login_view = '/'
    login_manager.session_protection = "strong"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(session_token):
        return manager.getUserObject(session_token)

    socketio.init_app(app)

    # Define Routs
    # Register
    app.add_url_rule("/register", view_func=VRegister.as_view("register", config, manager))
    # Login
    app.add_url_rule("/", view_func=VLogin.as_view("login", config, manager))
    # Lobby
    app.add_url_rule("/lobby", view_func=VLobby.as_view("lobby", config, manager))
    # Game
    app.add_url_rule("/game", view_func=VGame.as_view("game", config, manager))
    nsgame = NSGame("/game")
    nsgame.setup(config, manager)
    socketio.on_namespace(nsgame)

    socketio.run(app, port=config["server"]["port"], debug=config["server"]["debug"], host=config["server"]["host"])


if __name__ == '__main__':
    main()