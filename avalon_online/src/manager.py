#   Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
#   All rights reserved.
#   This file is part of the Avalon-NLU repository,
#   and is released under the "MIT License Agreement". Please see the LICENSE
#   file that should have been included as part of this package.

import sqlite3
import threading
from src.user import User
import re
import time
from src.game import Game
from hashids import Hashids
import time
import inspect

class Manager(object):
    def __init__(self, config, socketio):
        self._config = config
        self._max_players = config["game"]["max_players"]
        # This means we need to ensure only one thread at a time accesses this!!
        self._dbcon = sqlite3.connect("avalon.db", check_same_thread=False)
        self._db = self._dbcon.cursor()
        self._semaphore = threading.Semaphore(1) 
        self._active_games = {}
        self._idgen = Hashids()
        self._gidgen = Hashids(min_length=6)
        self._socketio = socketio
        self._locked = None
        self._lock_count = 0

    def _lockDB(self):
        # print("+++ Attempting Lock from:", inspect.stack()[1].function)
        if self._locked is not None: # Well, some thread already owns the database...
            if self._locked == threading.get_ident(): # If the re-lock is from the same thread, allow it
                self._lock_count += 1
                # print("  >>> Allowing additional lock for same thread:", self._lock_count)
                return
            else:
                pass
                # Note: This may not mean that we are in a dead lock, but rather that another request is waiting
                # print("  >>> Database already locked")
                # print(" << ".join(["{} (L{} | {})".format(v.function, v.lineno, v.filename.split("/")[-1]) for v in inspect.stack()]))
        self._semaphore.acquire()  # Acquire the lock
        self._locked = threading.get_ident()
        self._lock_count = 1

    def _unlockDB(self):
        # print("--- Unlocking from:", inspect.stack()[1].function)
        self._lock_count -= 1
        if self._lock_count == 0:
            self._locked = None
            self._semaphore.release()  # Release the lock
    
    def generateRandomID(self):
        mtime = time.time()
        keys = [int(v) for v in str(mtime).split(".")]
        return self._idgen.encode(keys[0], keys[1])

    def generateGameID(self, id):
        return self._gidgen.encode(id)

    def _userExists(self, name):
        res = self._db.execute(f"SELECT * FROM users WHERE name == '{name}'")
        return res.fetchone() is not None

    def registerUser(self, name, password, consent):
        self._lockDB()
        try:
            if self._userExists(name):
                return False, "A user with this name already exists"
            res = self._db.execute(f"INSERT INTO users (name, password, consent) VALUES ('{name}', '{password}', {consent})")
            self._dbcon.commit()
            return True, None
        finally:
            self._unlockDB()
    
    def getUserObject(self, session_token):
        self._lockDB()
        try:
            res = self._db.execute(f"SELECT * FROM users WHERE session_token == '{session_token}'")
            res = res.fetchall() 
            if len(res) == 0:
                return None
            elif len(res) == 1:
                return User(res[0])
            return None   
        finally:
            self._unlockDB()  

    def _setSessionToken(self, uid):
        print(uid)
        uid = re.findall(r'\d+', str(uid))[0]
        token = self.generateRandomID()
        self._db.execute(f"UPDATE users SET session_token = '{token}' WHERE id == {uid}")
        self._dbcon.commit()
        return token
    
    def loginUser(self, name, password):
        self._lockDB()
        try:
            res = self._db.execute(f"SELECT id FROM users WHERE name == '{name}' AND password == '{password}'")
            res = res.fetchall() 
            if len(res) == 0:
                return False, "Username or Password invalid", -1
            elif len(res) == 1:
                token = self._setSessionToken(res[0])
                return True, "", token
            else:
                print("Multiple users with same name and password detected... ouch")
        finally:
            self._unlockDB()

    def _getActiveGame(self, uid):
        res = self._db.execute(f"SELECT game FROM users WHERE id == {uid}")
        return res.fetchone()[0]
    
    def _getGameStatus(self, gid):
        res = self._db.execute(f"SELECT status FROM games WHERE id == {gid}")
        return res.fetchone()[0]

    def _clearActiveGameForPlayer(self, uid):
        self._db.execute(f"UPDATE users SET game = 0 WHERE id == {uid}")
        self._dbcon.commit()

    def _joinOrCreateGame(self, uid):
        open_games = self._findOpenGame(find_qp=True)
        open_games = [v[0] for v in open_games]
        if len(open_games) == 0:
            gid = self._createGame()
            return self._joinGame(uid, gid)
        else:
            return self._joinGame(uid, open_games[0])

    def _isGameFull(self, gid):
        open_games = self._findOpenGame(find_qp=False)
        open_games = [g[0] for g in open_games]
        if gid not in open_games:
            return True
        return False
    
    def _createGame(self, quickplay=True):
        ts = float(time.time())
        qp = 1 if quickplay else 0
        gameid = self._countAllGames()
        gameid = self.generateGameID(int(gameid)+1)
        self._db.execute(f"INSERT INTO games (status, timestamp, name, quickplay) VALUES ('waiting', {ts}, '{gameid}', {qp});")
        self._dbcon.commit()
        res = self._db.execute("SELECT last_insert_rowid();")
        res = res.fetchone()[0]
        return res

    def _joinGame(self, uid, gid):
        # Add the user to the games, but also start of the game if everyone is ready...
        self._db.execute(f"UPDATE users SET game = {gid} WHERE id == {uid};")
        self._dbcon.commit()
        # Let's check if the game is full... 
        self._createGameInstance(gid)
        self._joinUserToGameInstance(gid, uid)
        return gid
        
    def _findOpenGame(self, find_qp=True):
        fqp = str(1) if find_qp else str(0)
        res = self._db.execute(f"SELECT id FROM games WHERE status = 'waiting' AND quickplay == {fqp} AND id NOT IN (SELECT game FROM users GROUP BY game HAVING COUNT(*) >= {self._max_players});")
        res = res.fetchall()
        return res
    
    def countRunningGames(self):
        self._lockDB()
        try:
            res = self._db.execute("SELECT COUNT(*) AS running_game_count FROM games WHERE status = 'running';")
            res = res.fetchone()
            return res[0]
        finally:
            self._unlockDB()
    
    def _countAllGames(self):
        res = self._db.execute("SELECT COUNT(*) AS running_game_count FROM games;")
        res = res.fetchone()
        return res[0]
    
    def countOpenGames(self):
        self._lockDB()
        try:
            res = self._db.execute("SELECT COUNT(*) AS open_game_count FROM games WHERE status = 'waiting' AND quickplay == 1;")
            res = res.fetchone()
            return res[0]
        finally:
            self._unlockDB()
    
    def _countUsersInGame(self, gid):
        res = self._db.execute(f"SELECT COUNT(*) AS user_count FROM users WHERE game = {gid};")
        return res.fetchone()[0]
    
    def matchUserToGame(self, user):
        # This method has three main paths: Create a new game, joint a player to an existing game, or re-join player to an existing game
        self._lockDB()
        try:
            # Let's check if the player has an active game
            ag = self._getActiveGame(user.id)
            if ag > 0:
                if self._getGameStatus(ag) == "running":
                    # So they have an active game and it's still running
                    # Basically, rejoin the game
                    return self._joinGame(user.id, ag)
                else: # Clear finished or waiting games...
                    # They still have an active game listed, but the game is done, so let's remove it
                    self._clearActiveGameForPlayer(user.id)
            # This player is surely not in a game right now :) 
            return self._joinOrCreateGame(user.id)
        finally:
            self._unlockDB()
        
    def createGame(self, user):
        self._lockDB()
        try:
            # Let's check if the player has an active game
            ag = self._getActiveGame(user.id)
            if ag > 0:
                if self._getGameStatus(ag) == "running":
                    # So they have an active game and it's still running
                    # Basically, rejoin the game
                    return self._joinGame(user.id, ag)
                else: # Clear finished or waiting games...
                    # They still have an active game listed, but the game is done, so let's remove it
                    self._clearActiveGameForPlayer(user.id)
            # This player is surely not in a game right now :) 
            gid = self._createGame(quickplay=False)
            return self._joinGame(user.id, gid)
        finally:
            self._unlockDB()
    
    def joinGame(self, user, code):
        self._lockDB()
        try:
            # Let's check if the player has an active game
            ag = self._getActiveGame(user.id)
            if ag > 0:
                if self._getGameStatus(ag) == "running":
                    # So they have an active game and it's still running
                    # Basically, rejoin the game
                    return self._joinGame(user.id, ag)
                else: # Clear finished or waiting games...
                    # They still have an active game listed, but the game is done, so let's remove it
                    self._clearActiveGameForPlayer(user.id)
            # This player is surely not in a game right now :) 
            gid = self._getGameIDFromName(code)
            if gid:
                # Let's make sure the game is not already done.
                if self._isGameDoneOrNoneExistant(gid):
                    print("Game already finished... returning none")
                    return None
                # If it exists, is there still space?
                if self._isGameFull(gid):
                    print("Game Full... returning none")
                    return None
                return self._joinGame(user.id, gid)
            else: # Invalid game ID
                return None
        finally:
            self._unlockDB()

    def _isGameDoneOrNoneExistant(self, gid):
        res = self._db.execute(f"SELECT status FROM games WHERE id = '{gid}';")
        res = res.fetchone()
        if res is None:
            return True
        if res[0] != "finished":
            return False
        return True
    
    def _getGameIDFromName(self, name):
        res = self._db.execute(f"SELECT id FROM games WHERE name = '{name}';")
        res = res.fetchone()
        if res:
            return res[0]
        return None

    def _createGameInstance(self, gid):
        gname = self._getGameNameFromID(gid)
        if gid not in self._active_games.keys():
            self._active_games[gid] = Game(gid, self._config, self, gname, self._socketio)
    
    def _getGameNameFromID(self, gid):
        res = self._db.execute(f"SELECT name FROM games WHERE id = '{gid}';")
        res = res.fetchone()
        return res[0]

    def _joinUserToGameInstance(self, gid, uid):
        self._active_games[gid].addPlayer(uid)

    def getGame(self, gid):
        self._lockDB()
        try:
            if gid not in self._active_games.keys():
                return None
            return self._active_games[gid]
        finally:
            self._unlockDB()
    
    def getPlayerName(self, uid):
        self._lockDB()
        try:
            res = self._db.execute(f"SELECT name FROM users WHERE id == {uid}")
            return res.fetchone()[0]
        finally:
            self._unlockDB()
    
    def setGameStatus(self, gid, status):
        self._lockDB()
        try:
            self._db.execute(f"UPDATE games SET status = '{status}' WHERE id = {gid};")
            self._dbcon.commit()
        finally:
            self._unlockDB()

    def getGameName(self, gid):
        self._lockDB()
        try:
            res = self._db.execute(f"SELECT name FROM games WHERE id == {gid}")
            return res.fetchone()[0]
        finally:
            self._unlockDB()