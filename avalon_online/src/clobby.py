#   Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
#   All rights reserved.
#   This file is part of the Avalon-NLU repository,
#   and is released under the "MIT License Agreement". Please see the LICENSE
#   file that should have been included as part of this package.

from flask_socketio import Namespace, emit
from flask.views import MethodView
from flask import render_template, redirect, url_for
from flask_login import login_required, current_user, logout_user

class VLobby(MethodView):
    decorators = [login_required]

    def __init__(self, config, manager):
        self._config = config
        self._manager = manager
    
    def get(self):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        return render_template("lobby.html", user=current_user, rg=self._manager.countRunningGames(), og=self._manager.countOpenGames())

    def post(self):
        logout_user()
        return redirect(url_for("login"))