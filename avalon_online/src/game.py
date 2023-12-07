#   Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
#   All rights reserved.
#   This file is part of the Avalon-NLU repository,
#   and is released under the "MIT License Agreement". Please see the LICENSE
#   file that should have been included as part of this package.

from threading import Semaphore
import time
import random
from flask_login import current_user
from src.timer import RepeatedTimer
from enum import Enum
import numpy as np
from flask_socketio import emit
import time
from hashids import Hashids
from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage
from flask import current_app


class Player(object):
    def __init__(self, uid, index):
        self.id = uid
        self.name = ""
        self.last_active = 0
        self.role = None
        self.index = index

class GAME_STATE(Enum):
    PROPOSE_PARTY = 1
    PROPOSE_OR_PLAY = 2
    PLAYER_TURN = 3
    PARTY_VOTE_ACTIVE = 4
    IDLE = 5
    QUEST_VOTE_ACTIVE = 6
    ASSASSIN_VOTE_ACTIVE = 7
    FINISHED = 8

class GameDatabase(object):
    def __init__(self, name):
        self._db = TinyDB(f"logs/{name}.json", storage=JSONStorage)
        self._db.drop_tables()

        self._tbl_users = self._db.table("users")
        self._tbl_messages = self._db.table("messages")
        self._tbl_beliefs = self._db.table("beliefs")
        self._tbl_persuasion = self._db.table("persuasion")
        self._tbl_quests = self._db.table("quests")
        self._tbl_party = self._db.table("party")
        self._tbl_state = self._db.table("states")
    
    def savePlayers(self, players):
        for plr in players:
            self._tbl_users.insert({'id': plr.id, 'name': plr.name, 'role': plr.role, 'index': plr.index+1})
    
    def saveMessage(self, data):
        data = data.copy()
        data["ts"] = time.time()
        data.pop("strategy", None)
        self._tbl_messages.insert(data)
    
    def addBelief(self, data):
        data = data.copy()
        data["ts"] = time.time()
        self._tbl_beliefs.insert(data)

    def addPersuasion(self, data):
        data = data.copy()
        data["ts"] = time.time()
        self._tbl_persuasion.insert(data)
    
    def addQuestResult(self, qid, votes, result, party):
        data = {}
        data["ts"] = time.time()
        data["quest"] = qid
        data["votes"] = votes
        data["success"] = result
        data["party"] = [int(v) for v in party]
        self._tbl_quests.insert(data)
    
    def updatePartyVote(self, votes):
        did = self._tbl_party.all()[-1].doc_id
        self._tbl_party.update({"votes": votes}, doc_ids=[did])

    def proposeParty(self, party, failed, turn, quest, pid, automatic):
        data = {}
        data["ts"] = time.time()
        data["party"] = [int(v) for v in party]
        data["votes"] = [None, None, None, None, None, None]
        data["failed"] = failed
        data["turn"] = turn
        data["quest"] = quest
        data["pid"] = pid
        data["automatic"] = automatic
        self._tbl_party.insert(data)
    
    def addState(self, data):
        data["ts"] = time.time()
        self._tbl_state.insert(data)

class Game(object):
    def __init__(self, gid, config, manager, gname, socketio):
        self._gid = gid
        self._config = config
        self._manager = manager
        self._status = "waiting"
        self._players = []
        self.lock = Semaphore()
        self._idgen = Hashids()
        self._socketio = socketio

        # Server Heartbeat Thread
        self._timer = RepeatedTimer(self._config["game"]["turn_time"], self.endTurnTimer)
        self._voting_timer = RepeatedTimer(self._config["game"]["vote_time"], self.endTurnTimer)

        # Game-Related stuff:
        self._leader_pidx = -1
        self._turn_pidx = -1
        self._turn_start = 0
        self._turn_id = 1

        # Game State
        self._state = GAME_STATE.IDLE
        self._current_quest = 1
        self._proposed_party_idx = []
        self._failed_party_votes = 0
        self._quest_results = []
        self._winner = 0

        # Stuff
        self._game_db = GameDatabase(gname)
        self._msg_queue = []
    
    def generateRandomID(self):
        mtime = time.time()
        keys = [int(v) for v in str(mtime).split(".")]
        return self._idgen.encode(keys[0], keys[1])

    def _findPlayerByID(self, uid):
        for p in self._players:
            if p.id == uid:
                return p
        return None

    def findPlayerByID(self, uid):
        with self.lock:
            return self._findPlayerByID(uid)
    
    def _findPlayerByIndex(self, idx):
        for p in self._players:
            if p.index + 1 == int(idx):
                return p
        return None
    
    def findPlayerByIndex(self, idx):
        with self.lock:
            return self._findPlayerByIndex(idx)

    def addPlayer(self, uid):
        with self.lock:
            if self._findPlayerByID(uid) is None:
                plr = Player(uid, len(self._players))
                plr.name = self._manager.getPlayerName(uid)
                plr.last_active = time.time()
                self._players.append(plr)

            if len(self._players) == self._config["game"]["max_players"]:
                self._startGame()

    def _startGame(self):
        if self._status != "waiting":
            return
        self._manager.setGameStatus(self._gid, "running")
        self._status = "running"
        roles = self._config["game"]["roles"]
        random.shuffle(roles)
        for i in range(len(self._players)):
            self._players[i].role = roles[i]
        self._game_db.savePlayers(self._players)
        self._leader_pidx = self._findNextActivePlayer(random.randint(0,5))
        self._turn_pidx = self._leader_pidx
        self._turn_start = time.time()
        self._timer.startOnce()

        # Kick off the game...
        self._state = GAME_STATE.PROPOSE_PARTY
        self._addMessageToQueue(msg={
            'player': "system", 
            'msg': "Game Started!",
            'strategy': [],
            'pid': None,
            'mid': self.generateRandomID()
        }, room=self._gid)
    
    def _addMessageToQueue(self, msg, room):
        msg["quest"] = self._current_quest
        msg["turn"] = self._turn_id
        self._game_db.saveMessage(msg)
        self._msg_queue.append(('message', msg, room))

    def addMessageToQueue(self, msg, room):
        with self.lock:
            self._addMessageToQueue(msg, room)

    def endTurnTimer(self):
        with self.lock:
            self._nextPlayerOrVote(hb=True)

    def _nextPlayerOrVote(self, hb = False):
        if self._state == GAME_STATE.PROPOSE_PARTY:
            self._forceProposeParty()
            self._startNextPlayer()
        elif self._state == GAME_STATE.PLAYER_TURN and self._turn_pidx == self._leader_pidx and self._turn_id > 1 and hb:
            self._startVotingPhase()
        elif self._state == GAME_STATE.PLAYER_TURN:
            self._startNextPlayer()
        elif self._state == GAME_STATE.PARTY_VOTE_ACTIVE:
            self._forcePartyVote()
        elif self._state == GAME_STATE.QUEST_VOTE_ACTIVE:
            self._forceQuestVote()
        elif self._state == GAME_STATE.ASSASSIN_VOTE_ACTIVE:
            # Seems like the assassin didn't vote, so let's just say they didn't find merlin
            self._endGame(True)
        else:
            print("Turn timer ran out, but there is nothing to do! (This shoud not be happening)")

    def _forceQuestVote(self):
        for i in range(len(self._votes)):
            if self._votes[i] == None:
                self._votes[i] = True
        self._questVoteComplete()

    def _forcePartyVote(self):
        for i in range(len(self._votes)):
            if self._votes[i] == None:
                self._votes[i] = True
        self._addMessageToQueue(msg={
            'player': "system", 
            'msg': "Party Vote Outcome: " + ", ".join([f"{self._findPlayerByIndex(u+1).name}: {self._convertTrueFalse(v)}" for u, v in enumerate(self._votes)]),
            'strategy': [],
            'pid': None,
            'mid': self.generateRandomID()
        }, room=self._gid)
        self._partyVoteComplete()

    def startPartyVote(self, player):
        with self.lock:
            self._startVotingPhase()

    def _startVotingPhase(self):
        self._state = GAME_STATE.PARTY_VOTE_ACTIVE
        self._votes = [None for _ in range(self._config["game"]["max_players"])]
        self._timer.stop()
        self._voting_timer.startOnce()

    def _startNextPlayer(self):
        self._turn_pidx = self._findNextActivePlayer(self._turn_pidx)
        self._voting_timer.stop()
        self._timer.startOnce()
        self._turn_id += 1

    def _findNextActivePlayer(self, cid):
        steps = 0
        while True:
            steps += 1
            if steps > 10:
                print("Error: No players seem to be active (This is an unexpected problem...)")
                return 1
            cid = (cid + 1) % 6
            # This if is for debugging...
            if cid >= len(self._players):
                continue
            if self._players[cid].last_active + 1500 > time.time():
                break
        return cid

    def _forceProposeParty(self):
        self._state = GAME_STATE.PLAYER_TURN
        self._proposed_party_idx = np.random.choice(
            [1,2,3,4,5,6], 
            size=self._config["game"]["quest_party_size"][self._current_quest-1], 
        replace=False).tolist()
        party = ", ".join([self._findPlayerByIndex(i).name for i in self._proposed_party_idx])
        self._addMessageToQueue(msg={
            'player': "system", 
            'msg': "Automatic party proposal: " + party,
            'strategy': [],
            'pid': None,
            'mid': self.generateRandomID()
        }, room=self._gid)
        self._game_db.proposeParty(self._proposed_party_idx, self._failed_party_votes, self._turn_id, self._current_quest, self._leader_pidx+1, automatic=True)

    def heartbeat(self, uid):
        with self.lock:
            plr = self._findPlayerByID(uid)
            if plr:
                plr.last_active = time.time()
            # Check if there are messages in the queue
            for data in self._msg_queue:
                emit(data[0], data[1], room=data[2])
            self._msg_queue = []

    def _findPlayerKnowledge(self, uid):
        if self._status != "running":
            return []
        plr = self._findPlayerByID(uid)
        knowledge = []
        for plr2 in self._players:
            if plr == plr2:
                continue
            # Evil knows eachother
            if ((plr.role == "assassin" or plr.role == "morgana" or plr.role == "minion") and
                (plr2.role == "assassin" or plr2.role == "morgana" or plr2.role == "minion")):
                knowledge.append((plr2.index+1, "evil"))
            # Merlin knows evil
            elif ((plr.role == "merlin") and
                (plr2.role == "assassin" or plr2.role == "morgana" or plr2.role == "minion")):
                knowledge.append((plr2.index+1, "evil"))
            # Percival knows Morgana and Merlin
            elif ((plr.role == "percival") and
                (plr2.role == "merlin" or plr2.role == "morgana")):
                knowledge.append((plr2.index+1, "unknown"))
        return knowledge

    def getState(self):
        with self.lock:
            return self._getState()
    
    def _getSaveState(self):
        return {
            "players": [p.name for p in self._players],
            "active": [p.last_active + 1500 > time.time() for p in self._players],
            "status": self._status,
            "winner": self._winner,
            "leader_pid": self._leader_pidx+1,
            "turn_pid": self._turn_pidx+1,
            "party": self._proposed_party_idx,
        }

    def _getState(self):
        plr = self._findPlayerByID(current_user.id)
        knowledge = self._findPlayerKnowledge(current_user.id)
        state = {
            "players": [p.name for p in self._players],
            "active": [p.last_active + 1500 > time.time() for p in self._players],
            "status": self._status,
            "winner": self._winner,
        }
        can_propose_party = (self._state == GAME_STATE.PROPOSE_PARTY or self._state == GAME_STATE.PLAYER_TURN) and self._leader_pidx == plr.index and self._turn_pidx == plr.index
        can_start_party_vote = self._state == GAME_STATE.PLAYER_TURN and self._turn_pidx == plr.index and len(self._proposed_party_idx) > 0 and self._turn_id > 1 and self._leader_pidx == plr.index
        can_vote_quest = self._state == GAME_STATE.QUEST_VOTE_ACTIVE and plr.index + 1 in [int(v) for v in self._proposed_party_idx]
        can_vote_party = self._state == GAME_STATE.PARTY_VOTE_ACTIVE
        can_vote_assassin = False

        if plr:
            can_vote_assassin = plr.role == "assassin" and self._state == GAME_STATE.ASSASSIN_VOTE_ACTIVE

        if self._state != GAME_STATE.IDLE and self._state != GAME_STATE.FINISHED:
            state = {
                "players": [p.name for p in self._players],
                "active": [p.last_active + 1500 > time.time() for p in self._players],
                "status": self._status,
                "winner": self._winner,
                "role": plr.role,
                "pid": plr.index + 1,
                "knowledge": knowledge,
                "progress": self._getTimerValue(),
                "leader_pid": self._leader_pidx+1,
                "turn_pid": self._turn_pidx+1,
                "can_propose_party": self._config["game"]["quest_party_size"][self._current_quest-1] if can_propose_party else -1,
                "party": self._proposed_party_idx,
                "vote_party": can_vote_party,
                "enable_party_vote_option": can_start_party_vote,
                "quest_results": self._quest_results,
                "failed_party_votes": self._failed_party_votes,
                "vote_quest": can_vote_quest,
                "vote_assassin": can_vote_assassin,
                "all_roles": [],
            }
        elif self._state == GAME_STATE.FINISHED:
            # Let's reveal roles
            state = {
                "players": [p.name for p in self._players],
                "active": [p.last_active + 1500 > time.time() for p in self._players],
                "status": self._status,
                "winner": self._winner,
                "role": plr.role,
                "pid": plr.index + 1,
                "knowledge": knowledge,
                "progress": 0,
                "leader_pid": None,
                "turn_pid": None,
                "can_propose_party": -1,
                "party": [],
                "vote_party": False,
                "enable_party_vote_option": False,
                "quest_results": self._quest_results,
                "failed_party_votes": self._failed_party_votes,
                "vote_quest": False,
                "vote_assassin": False,
                "all_roles": [p.role for p in self._players],
            }

        return state
        
    def _getTimerValue(self):
        if self._state == GAME_STATE.PARTY_VOTE_ACTIVE or self._state == GAME_STATE.QUEST_VOTE_ACTIVE:
            return [1-float(self._voting_timer.getRemaining()) / self._config["game"]["vote_time"], self._config["game"]["vote_time"], self._voting_timer.is_running]
        return [1-float(self._timer.getRemaining()) / self._config["game"]["turn_time"], self._config["game"]["turn_time"], self._timer.is_running]
    
    def endCurrentPlayerTurn(self, pidx):
        with self.lock:
            # Prevent the leaer to end their turn when a vote is active and thus force success
            if self._state == GAME_STATE.PARTY_VOTE_ACTIVE or self._state == GAME_STATE.QUEST_VOTE_ACTIVE:
                return
            if self._turn_pidx != pidx-1:
                return
            self._timer.stop()
            self._nextPlayerOrVote()

    def partyProposal(self, pidx, partyidx):
        with self.lock:
            if len(partyidx) != self._config["game"]["quest_party_size"][self._current_quest - 1]:
                print("Error: Proposed party size is invalid... (This should never happen!)")
            self._proposed_party_idx = partyidx
            self._game_db.proposeParty(self._proposed_party_idx, self._failed_party_votes, self._turn_id, self._current_quest, pidx, automatic=False)
            self._state = GAME_STATE.PLAYER_TURN

    def _convertTrueFalse(self, v):
        if v:
            return "Yes"
        return "No"

    def updateVote(self, uid, vote):
        with self.lock:
            plr = self._findPlayerByID(uid)
            if self._state == GAME_STATE.PARTY_VOTE_ACTIVE:
                self._votes[plr.index] = vote
                if None not in self._votes:
                    self._voting_timer.stop()
                    self._addMessageToQueue(msg={
                        'player': "system", 
                        'msg': "Party Vote Outcome: " + ", ".join([f"{self._findPlayerByIndex(u+1).name}: {self._convertTrueFalse(v)}" for u, v in enumerate(self._votes)]),
                        'strategy': [],
                        'pid': None,
                        'mid': self.generateRandomID()
                    }, room=self._gid)
                    self._partyVoteComplete()
            elif self._state == GAME_STATE.QUEST_VOTE_ACTIVE:
                # print("got a quest vote", uid, plr.index + 1, vote)
                for i in range(len(self._proposed_party_idx)):
                    # print("Party:", self._proposed_party_idx[i], plr.index + 1, plr.index + 1 == int(self._proposed_party_idx[i]))
                    if plr.index + 1 == int(self._proposed_party_idx[i]):
                        self._votes[i] = vote
                # print("Votes", self._votes)
                if None not in self._votes:
                    self._voting_timer.stop()
                    # print("Got in all votes!")
                    self._questVoteComplete()
    
    def _questVoteComplete(self):
        self._voting_timer.stop()
        if False in self._votes:
            self._addMessageToQueue(msg={
                'player': "system", 
                'msg': "Quest Failed! ",
                'strategy': [],
                'pid': None,
                'mid': self.generateRandomID()
            }, room=self._gid)
            result = False
        else:
            self._addMessageToQueue(msg= {
                'player': "system", 
                'msg': "Quest Succeeded!",
                'strategy': [],
                'pid': None,
                'mid': self.generateRandomID()
            }, room=self._gid)
            result = True
        self._makeQuestResult(result)
        self._resetClientStates()

    def _partyVoteComplete(self):
        self._voting_timer.stop()
        self._game_db.updatePartyVote(self._votes)
        cnt = None
        tp, cnts = np.unique(self._votes, return_counts=True)
        for i in range(len(tp)):
            if tp[i]:
                cnt = cnts[i]
        if not cnt:
            cnt = 0
        if cnt > len(self._votes)/2.0:
            self._addMessageToQueue(msg= { 
                'player': "system", 
                'msg': "Vote Succeeded! Initiating Quest Vote!",
                'strategy': [],
                'pid': None,
                'mid': self.generateRandomID()
            }, room=self._gid)
            self._startQuestVote()
        else:
            self._addMessageToQueue(msg={
                'player': "system", 
                'msg': "Vote Failed!",
                'strategy': [],
                'pid': None,
                'mid': self.generateRandomID()
            }, room=self._gid)
            self._failedPartyVote()
        self._resetClientStates()

    def _resetClientStates(self):
        self._msg_queue.append(('reset', {}, self._gid))

    def _failedPartyVote(self):
        self._failed_party_votes += 1
        if self._failed_party_votes >= 5:
            self._votes = [None for _ in range(self._config["game"]["quest_party_size"][self._current_quest-1])]
            self._makeQuestResult(False)
        else:
            self._leader_pidx = self._findNextActivePlayer(self._leader_pidx)
            self._turn_pidx = self._leader_pidx
            self._turn_id = 1
            self._proposed_party_idx = []
            self._state = GAME_STATE.PROPOSE_PARTY
            self._voting_timer.stop()
            self._timer.startOnce()
    
    def _startQuestVote(self):
        self._state = GAME_STATE.QUEST_VOTE_ACTIVE
        self._timer.stop()
        self._voting_timer.startOnce()
        self._votes = [None for _ in range(len(self._proposed_party_idx))]

    def _makeQuestResult(self, outcome):
        self._game_db.addState(self._getSaveState())
        self._game_db.addQuestResult(self._current_quest, self._votes, outcome, self._proposed_party_idx)
        self._quest_results.append(outcome)
        self._failed_party_votes = 0
        self._leader_pidx = self._findNextActivePlayer(self._leader_pidx)
        self._turn_pidx = self._leader_pidx
        self._turn_id = 1
        self._proposed_party_idx = []
        self._current_quest += 1
        self._state = GAME_STATE.PROPOSE_PARTY
        self._checkFinishGame()

        if self._state != GAME_STATE.FINISHED:
            self._voting_timer.stop()
            self._timer.startOnce()

    def _checkFinishGame(self):
        qr, cnts = np.unique(self._quest_results, return_counts=True) 
        for i in range(len(qr)):
            if qr[i] and cnts[i] >= 3:
                self._state = GAME_STATE.ASSASSIN_VOTE_ACTIVE
                self._setTurnToAssassin()
                self._addMessageToQueue(msg={
                'player': "system", 
                'msg': "Good won for now, but the Assassin...",
                'strategy': [],
                'pid': None,
                'mid': self.generateRandomID()
            }, room=self._gid)
            elif not qr[i] and cnts[i] >= 3:
                self._endGame(False)
    
    def _setTurnToAssassin(self):
        self._timer.stop()
        for plr in self._players:
            if plr.role == "assassin":
                self._turn_pidx = plr.index
                self._timer.startOnce()
                self._turn_id += 1

    def _endGame(self, good_wins, via_assassin=False):
        if(good_wins):
            self._winner = 1
            self._addMessageToQueue(msg={
                'player': "system", 
                'msg': "The Assassin dind't find Merlin, thus the forces of Good win!",
                'strategy': [],
                'pid': None,
                'mid': self.generateRandomID()
            }, room=self._gid)
        else:
            self._winner = -1
            if via_assassin:
                self._addMessageToQueue(msg={
                    'player': "system", 
                    'msg': "The Assassin identified Merlin, thus Evil wins!",
                    'strategy': [],
                    'pid': None,
                    'mid': self.generateRandomID()
                }, room=self._gid)
            else:
                self._addMessageToQueue(msg={
                    'player': "system", 
                    'msg': "Evil has failed three quests and wins!",
                    'strategy': [],
                    'pid': None,
                    'mid': self.generateRandomID()
                }, room=self._gid)
        self._game_db.addState(self._getSaveState())
        self._state = GAME_STATE.FINISHED
        self._manager.setGameStatus(self._gid, "finished")
    
    def saveMessage(self, msg):
        with self.lock:
            msg["quest"] = self._current_quest
            msg["turn"] = self._turn_id
            self._game_db.saveMessage(msg)

    def saveBelief(self, data):
        with self.lock:
            data = data.copy()
            data["quest"] = self._current_quest
            data["turn"] = self._turn_id
            self._game_db.addBelief(data)
    
    def savePersuasion(self, data):
        with self.lock:
            # Add some fancy stuff here...
            data = data.copy()
            data["quest"] = self._current_quest
            data["turn"] = self._turn_id
            self._game_db.addPersuasion(data)

    def updateAssassinVote(self, data):
        with self.lock:
            print("Assassin Choice", data)
            plr = self._findPlayerByIndex(data["guess"])
            data = data.copy()
            data["quest"] = self._current_quest
            data["turn"] = self._turn_id
            self._game_db.addBelief(data)
            if plr.role == "merlin": # Assassin Won
                self._endGame(False, via_assassin=True)
            else:
                self._endGame(True, via_assassin=True)