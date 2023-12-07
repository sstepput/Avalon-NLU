#   Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
#   All rights reserved.
#   This file is part of the Avalon-NLU repository,
#   and is released under the "MIT License Agreement". Please see the LICENSE
#   file that should have been included as part of this package.

from flask_socketio import Namespace, emit, join_room, leave_room
from flask.views import MethodView
from flask import render_template, redirect, url_for, request
from flask_login import login_required, current_user, logout_user
import time
from hashids import Hashids
from bs4 import BeautifulSoup

class VGame(MethodView):
    decorators = [login_required]

    def __init__(self, config, manager):
        self._manager = manager
        self._config = config

    def get(self):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        
        if "game-type" not in request.args.keys():
            print("No form data in join request... returning")
            return redirect(url_for("lobby"))
        
        room = None
        join_type = request.args["game-type"]
        if join_type == "Quickplay":
            room = self._manager.matchUserToGame(current_user)
        elif join_type == "Create Game":
            room = self._manager.createGame(current_user)
        elif join_type == "Join Game":
            room = self._manager.joinGame(current_user, request.args["game-id"])

        if room is None:
            return redirect(url_for("lobby"))
        
        gname = self._manager.getGameName(room)
        current_user.game = room

        return render_template("game.html", gid=gname, qsize=self._config["game"]["quest_party_size"])
    
    def post(self):
        logout_user()
        return redirect(url_for("login"))

class NSGame(Namespace):
    def setup(self, config, manager):
        self._config = config
        self._manager = manager
        self._idgen = Hashids()
    
    def generateRandomID(self):
        mtime = time.time()
        keys = [int(v) for v in str(mtime).split(".")]
        return self._idgen.encode(keys[0], keys[1])

    def on_connect(self):
        pass

    def on_disconnect(self):
        pass
    
    def on_heartbeat(self, data):
        if current_user.is_anonymous:
            return
        game = self._manager.getGame(current_user.game)
        if game:
            game.heartbeat(current_user.id)
            emit("state", game.getState())

    def on_joined(self, msg):
        if current_user.is_anonymous:
            return
        join_room(current_user.game)
        game = self._manager.getGame(current_user.game)
        if game:
            emit("state", game.getState())

    def on_text(self, data):
        game = self._manager.getGame(current_user.game)
        plr = None if not game else game.findPlayerByID(current_user.id)
        pidx = None if not plr else plr.index+1
        msg = BeautifulSoup(data["msg"], "lxml").text
        if msg == "":
            return
        content = {
            'pid': pidx, 
            'player': current_user.name, 
            'strategy': self._config["game"]["persuasion_strategy"], 
            'msg': msg,
            'mid': self.generateRandomID()
        }
        emit('message', content, room=current_user.game)
        if game:
            game.saveMessage(content)
    
    def on_end_turn(self, data):
        game = self._manager.getGame(current_user.game)
        if game:
            game.endCurrentPlayerTurn(data["player"])
            emit("state", game.getState(), room=current_user.game)

    def on_vote_confirm(self, data):
        game = self._manager.getGame(current_user.game)
        if game:
            game.partyProposal(data["player"], data["party"])
            print(data["party"])
            party = ", ".join([game.findPlayerByIndex(i).name for i in data["party"]])
            game.addMessageToQueue(msg={
                'player': "system", 
                'msg':current_user.name + " proposed a party: " + party,
                'strategy': [],
                'pid': None,
                'mid': self.generateRandomID()
            }, room=current_user.game)
            emit("state", game.getState(), room=current_user.game)

    def on_vote_yes(self, data):
        game = self._manager.getGame(current_user.game)
        if game:
            game.updateVote(current_user.id, data["vote"])
            emit("state", game.getState())

    def on_vote_no(self, data):
        game = self._manager.getGame(current_user.game)
        if game:
            game.updateVote(current_user.id, data["vote"])
            emit("state", game.getState())

    def on_start_party_vote(self, data):
        game = self._manager.getGame(current_user.game)
        if game:
            game.startPartyVote(data["player"])
            emit("state", game.getState(), room=current_user.game)

    def on_persuasion(self, data):
        game = self._manager.getGame(current_user.game)
        if game:
            game.savePersuasion(data)

    def on_belief(self, data):
        game = self._manager.getGame(current_user.game)
        if game:
            game.saveBelief(data)

    def on_typing(self, data):
        game = self._manager.getGame(current_user.game)
        if game and "player" in data.keys():
            emit('is_typing', {'player': game.findPlayerByIndex(data["player"]).name}, room=current_user.game)
    
    def on_assassin_vote(self, data):
        game = self._manager.getGame(current_user.game)
        if game:
            game.updateAssassinVote(data)