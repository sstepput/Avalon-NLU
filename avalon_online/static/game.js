/*
    Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
    All rights reserved.
    This file is part of the Avalon-NLU repository,
    and is released under the "MIT License Agreement". Please see the LICENSE
    file that should have been included as part of this package.
*/

var socket = null;
var LAST_TYPING_TS = 0;
var LAST_TYPING_UPDATE = 0;
var PLAYER = null;
var PROGRESS = [0, 5, false];
var PARTY_SELECT = [];
var TARGET_PARTY_SIZE = -1;
var ACTIVE_PARTY = [];
var VOTE_INCOMPLETE = true;
var VOTE_QUEST_INCOMPLETE = true;
var VOTE_ASSASSIN_INCOMPLETE = true;
var MERLIN_CHOICE = null;
var ASSASSIN_VOTE = false;
var FORCE_WAIT_STATUS = false;

var HEARTBEAT = window.setInterval(function() {
    if (LAST_TYPING_UPDATE + 4 < getTimestampInSeconds()) {
        document.getElementById("x_is_typing").innerHTML = "";
    }

    if (socket != null) {
        socket.emit("heartbeat", {})
    }

}, 1000);

var ANIMATION = window.setInterval(function() {
    if (PROGRESS[2]) {
        PROGRESS[0] += (150 / PROGRESS[1] / 10.0) / 150.0;
        PROGRESS[0] = Math.min(PROGRESS[0], 1.0);
        var clr = "rgb(237, 123, 30)";
        if (PROGRESS[0] > 0.9) {
            clr = "red";
        }
        pgrs = "width: " + Math.ceil(150 * PROGRESS[0]) + "px; background-color: " + clr + ";";

        document.getElementById("loading-bar-progress").style = pgrs;
    }
}, 100);

function getTimestampInSeconds() {
    return Math.floor(Date.now() / 1000)
}

function updateScroll() {
    var element = document.getElementById("chat");
    element.scrollTop = element.scrollHeight;
}

function selected_for_party(event) {
    var clickedImage = event.target;
    var imageId = clickedImage.id;
    var player_index = imageId.split("-").pop();
    if (ASSASSIN_VOTE) {
        assassin_vote_handler(player_index);
    } else {
        party_vote_handler(player_index);
    }
}

function assassin_vote_handler(pid) {
    var xmark = document.getElementById("x-mark-" + pid);
    if (xmark.style.display === "none") {
        xmark.style = "display: block";
        if (MERLIN_CHOICE != null) {
            document.getElementById("x-mark-" + MERLIN_CHOICE).style = "display: none";
        }
        MERLIN_CHOICE = pid;
    }
    document.getElementById("vote_assassin_button").disabled = MERLIN_CHOICE == null;
}

function party_vote_handler(pid) {
    if (TARGET_PARTY_SIZE <= 0) {
        return;
    }

    var shield = document.getElementById("shield-" + pid);
    if (shield.style.display === "none") {
        shield.style.display = "block";
        PARTY_SELECT.push(parseInt(pid));
        // console.log("Adding", shield.id, PARTY_SELECT)
    } else {
        shield.style.display = "none";
        var index = PARTY_SELECT.indexOf(parseInt(pid));
        if (index !== -1) {
            PARTY_SELECT.splice(index, 1);
        }
        // console.log("Removing", shield.id, PARTY_SELECT)
    }
    document.getElementById("voting-task").innerHTML = "Propose a party of " + TARGET_PARTY_SIZE + "!<br>Selected Size: " + PARTY_SELECT.length + "/" + TARGET_PARTY_SIZE;
    document.getElementById("vote_confirm_button").disabled = TARGET_PARTY_SIZE != PARTY_SELECT.length;
    if (arraysAreEqual(PARTY_SELECT, ACTIVE_PARTY)) {
        document.getElementById("vote_confirm_button").disabled = true;
    }
}

function arraysAreEqual(arr1, arr2) {
    if (arr1.length !== arr2.length) {
        return false;
    }

    var sortedArr1 = arr1.slice().sort();
    var sortedArr2 = arr2.slice().sort();

    for (var i = 0; i < sortedArr1.length; i++) {
        if (sortedArr1[i] !== sortedArr2[i]) {
            return false;
        }
    }

    return true;
}

function resetState(role) {
    for (let i = 0; i < 6; i++) {
        var pid = i + 1
        document.getElementById("player-name-" + pid).innerHTML = "";
        document.getElementById("player-predicted-role-" + pid).innerHTML = "";
        document.getElementById("player-portret-" + pid).style = "display: none";
        document.getElementById("player-portret-" + pid).src = "static/assets/empty.png";
        document.getElementById("disconnected-" + pid).style = "display:block";
        document.getElementById("crown-" + pid).style = "display:none";
        document.getElementById("jester-" + pid).style = "display:none";

        // Always clear shields unless the current player is the leader and currently allowed to vote
        if (TARGET_PARTY_SIZE <= 0) {
            document.getElementById("shield-" + pid).style = "display:none";
        }
        document.getElementById("evil-ring-" + pid).style = "display:none;";
        document.getElementById("good-ring-" + pid).style = "display:none;";
        document.getElementById("unknown-ring-" + pid).style = "display:none;";

        if (pid == PLAYER) {
            document.getElementById("player-belief-" + pid).style = "display:none";
            document.getElementById("player-predicted-role-" + pid).innerHTML = role;
        } else {
            document.getElementById("player-belief-" + pid).style = "display:block";
        }
    }

    // NOTE: Party Images are only 5
    for (var i = 1; i < 6; i++) {
        document.getElementById("party-image-" + i).style = "display:none";
    }
    // document.getElementById("text").disabled = true; # Chrome doesn't like this...
    document.getElementById("end_turn_button").style = "display:none;";
    document.getElementById("vote_yes_button").style = "display:none;";
    document.getElementById("vote_no_button").style = "display:none;";
    document.getElementById("vote_confirm_button").style = "display:none;";
    document.getElementById("voting-task").style = "display:none;";
    document.getElementById("vote_party_button").style = "display:none;";
    document.getElementById("vote_assassin_button").style = "display:none;";
}

function selectPersuasion(id) {
    var select = document.getElementById(id);
    select.style = "display:none";
    mid = id.split("-")[1];
    socket.emit('persuasion', { 'player': PLAYER, 'mid': mid, 'persuasion': select.value });
}

function selectBelief(id) {
    pid = parseInt(id.split("-")[2]);
    socket.emit('belief', { 'player': PLAYER, 'about_player': pid,'belief': document.getElementById(id).value })
}

$(document).ready(function() {
    document.getElementById("vote_confirm_button").disabled = true;
    document.getElementById("vote_assassin_button").disabled = true;

    url = 'http://' + document.domain + ':' + location.port + '/game';
    socket = io.connect(url);

    socket.on('connect', function() {
        socket.emit('joined', {});
    });

    socket.on('message', function(data) {

        slct = '<select id="strategy-' + data.mid + '" onchange="selectPersuasion(this.id)"> <option value="" disabled selected>Persuasion Strategy</option>';
        for (const v of data.strategy) {
            slct += '<option value="' + v.toLowerCase() + '">' + v + '</option>';
        }
        slct += '</select>';
        var iDiv = document.createElement('div');
        iDiv.className = 'message-container';
        if (PLAYER == data.pid && PLAYER != null) {
            iDiv.style = "background-color: rgba(0, 255, 191, 0.3);";
        } else if (data.player === "system") {
            iDiv.style = "background-color: rgba(255, 0, 191, 0.3);";
            slct = "";
        } else {
            slct = "";
        }
        iDiv.innerHTML = "<div class='message-strategy'>" + slct + "</div><div class='message-inner'>" + data.player + ": " + data.msg + "</div>";
        document.getElementById('chat').appendChild(iDiv);
        updateScroll();
    });

    socket.on('is_typing', function(data) {
        LAST_TYPING_UPDATE = getTimestampInSeconds();
        document.getElementById("x_is_typing").innerHTML = data.player + " is typing..."
    });

    socket.on('reset', function(data) {
        PARTY_SELECT = [];
        TARGET_PARTY_SIZE = -1;
        VOTE_INCOMPLETE = true;
        VOTE_QUEST_INCOMPLETE = true;
        VOTE_ASSASSIN_INCOMPLETE = true;
        MERLIN_CHOICE = null;
        ASSASSIN_VOTE = false;
    });

    socket.on('state', function(data) {
        console.log(data)
        // Set this once... and hope for the best
        if (PLAYER == null) {
            PLAYER = data.pid;
        }
        
        // If we get the state for another user, ignore it...
        if (PLAYER != data.pid) {
            console.log("Got a state for an unexpected user. I am " + PLAYER + " but got a state for player " + data.pid)
            return
        }

        resetState(data.role)
        active = data.status == "running";
        
        // Update the stuff
        for (let i = 0; i < data.players.length; i++) {
            var pid = i + 1
            document.getElementById("player-name-" + pid).innerHTML = data.players[i];
            if (data.active[i]) {
                document.getElementById("disconnected-" + pid).style = "display:none";
            }
        }

        // CUTOFF for ACTIVE
        if (!active) {
            return;
        }
        PROGRESS = data.progress;

        // if (data.pid != data.turn_pid) {
        //     PARTY_SELECT = [];
        // }

        for (let i = 0; i < data.players.length; i++) {
            var pid = i + 1
            // console.log(data.knowledge);
            for (const k of data.knowledge) {
                document.getElementById(k[1] + "-ring-" + k[0]).style = "display: block";
            }
        }

        if (data.role != null) {
            document.getElementById("player-portret-" + data.pid).style = "display: block";
            document.getElementById("player-portret-" + data.pid).src = "static/assets/" + data.role + ".png";
        }

        if (data.leader_pid != null && data.turn_pid != null) {
            document.getElementById("crown-" + data.leader_pid).style = "display: block"
            document.getElementById("jester-" + data.turn_pid).style = "display: block"
        }


        if (data.pid == data.turn_pid && !data.vote_party) {
            document.getElementById("text").disabled = false;
            document.getElementById("end_turn_button").style = "display: block;";
        } else {
            document.getElementById("text").disabled = true;
        }

        if (data.can_propose_party > 0 && !data.vote_assassin) {
            document.getElementById("vote_confirm_button").style = "display:block;";
            document.getElementById("voting-task").innerHTML = "Propose a party of " + data.can_propose_party + "!<br>Selected Size: " + PARTY_SELECT.length + "/" + data.can_propose_party;
            document.getElementById("voting-task").style = "display:block;";
            if (PARTY_SELECT.length == 0 && data.party.length > 0) {
                PARTY_SELECT = data.party;
            }
            for (const k of PARTY_SELECT) {
                // console.log("Drawing shields in line 270", PARTY_SELECT)
                document.getElementById("shield-" + k).style = "display: block";
            }
        } else {
            // For every non-leader, set this select to []. This will draw the shields
            PARTY_SELECT = [];
        }
        TARGET_PARTY_SIZE = data.can_propose_party;

        // This is for every non-leader player
        if (PARTY_SELECT.length == 0) {
            for (const k of data.party) {
                // console.log("Drawing shields in line 283")
                document.getElementById("shield-" + k).style = "display: block";
            }
        }

        if (data.enable_party_vote_option) {
            document.getElementById("vote_party_button").style = "display:block;";
        }

        document.getElementById("vote_party_button").disabled = !arraysAreEqual(PARTY_SELECT, data.party);
        ACTIVE_PARTY = data.party;
        if (arraysAreEqual(PARTY_SELECT, data.party)) {
            document.getElementById("vote_confirm_button").disabled = true;
        }

        if (data.vote_party && VOTE_INCOMPLETE) {
            document.getElementById("vote_yes_button").style = "display:block;background-color:lightskyblue;";
            document.getElementById("vote_no_button").style = "display:block;background-color:lightskyblue;";
            document.getElementById("vote_yes_button").innerHTML = "Absolutely!";
            document.getElementById("vote_no_button").innerHTML = "Never!";
            document.getElementById("voting-task").innerHTML = "Do you approve the current party?";
            document.getElementById("voting-task").style = "display:block;";
        }

        if (!data.vote_party) {
            // If this is ever false, it means the vote from the server completed, so we can reset that here...
            VOTE_INCOMPLETE = true;
        }

        if (!data.vote_quest) {
            VOTE_QUEST_INCOMPLETE = true;
        }

        if (!data.vote_assassin) {
            VOTE_ASSASSIN_INCOMPLETE = true;
        }

        if (data.vote_quest && VOTE_QUEST_INCOMPLETE) {
            document.getElementById("vote_yes_button").style = "display:block;background-color:burlywood;";
            document.getElementById("vote_no_button").style = "display:block;background-color:burlywood;";
            document.getElementById("vote_yes_button").innerHTML = "Succeed!";
            document.getElementById("vote_no_button").innerHTML = "Fail It!";
            document.getElementById("voting-task").innerHTML = "Should the quest succeed?";
            document.getElementById("voting-task").style = "display:block;";
        }

        if (data.vote_assassin && VOTE_ASSASSIN_INCOMPLETE) {
            ASSASSIN_VOTE = true;
            document.getElementById("vote_assassin_button").style = "display:block;";
            document.getElementById("voting-task").innerHTML = "Who is Merlin?";
            document.getElementById("voting-task").style = "display:block;";
            document.getElementById("end_turn_button").style = "display:none;";
        }

        for (var i = 1; i <= data.failed_party_votes; i++) {
            document.getElementById("party-image-" + i).style = "display:block";
        }

        for (var i = 0; i < data.quest_results.length; i++) {
            document.getElementById("quest-image-" + (i + 1)).style = "display:block";
            if (data.quest_results[i]) {
                document.getElementById("quest-image-" + (i + 1)).src = "static/assets/quest-success.png";
            } else {
                document.getElementById("quest-image-" + (i + 1)).src = "static/assets/quest-fail.png";
            }
        }

        for (var i = 0; i < data.all_roles.length; i++) {
            var pid = i + 1
            document.getElementById("player-portret-" + pid).style = "display: block";
            document.getElementById("player-portret-" + pid).src = "static/assets/" + data.all_roles[i] + ".png";
        }

        if (data.winner == 1) {
            document.getElementById("voting-task").innerHTML = "Winner: Good!";
            document.getElementById("voting-task").style = "display:block;";
        } else if (data.winner == -1) {
            document.getElementById("voting-task").innerHTML = "Winner: Evil!";
            document.getElementById("voting-task").style = "display:block;";
        }

        // Reset the force-wait:
        FORCE_WAIT_STATUS = false;
    });

    document.getElementById("end_turn_button").addEventListener("click", function() {
        socket.emit('end_turn', { "player": PLAYER });
    });

    document.getElementById("vote_yes_button").addEventListener("click", function() {
        socket.emit('vote_yes', { "player": PLAYER, "vote": true });
        VOTE_INCOMPLETE = false;
        VOTE_QUEST_INCOMPLETE = false;
    });

    document.getElementById("vote_no_button").addEventListener("click", function() {
        socket.emit('vote_no', { "player": PLAYER, "vote": false });
        VOTE_INCOMPLETE = false;
        VOTE_QUEST_INCOMPLETE = false;
    });

    document.getElementById("vote_confirm_button").addEventListener("click", function() {
        if (!FORCE_WAIT_STATUS) {
            socket.emit('vote_confirm', { "player": PLAYER, "party": PARTY_SELECT });
            PARTY_SELECT = [];
            FORCE_WAIT_STATUS = true;
        }
    });

    document.getElementById("vote_party_button").addEventListener("click", function() {
        socket.emit('start_party_vote', { "player": PLAYER });
        PARTY_SELECT = [];
    });

    document.getElementById("vote_assassin_button").addEventListener("click", function() {
        socket.emit('assassin_vote', { "player": PLAYER, "guess": MERLIN_CHOICE });
        MERLIN_CHOICE = null;
        ASSASSIN_VOTE = false;
        VOTE_ASSASSIN_INCOMPLETE = false;
    });

    // People with special knowledge need a separate handler....
    for (var i = 1; i <= 6; i++) {
        document.getElementById("good-ring-" + i).addEventListener("click", function(event) {
            selected_for_party(event);
        });
        document.getElementById("evil-ring-" + i).addEventListener("click", function(event) {
            selected_for_party(event);
        });
        document.getElementById("unknown-ring-" + i).addEventListener("click", function(event) {
            selected_for_party(event);
        });
    }

    $('#text').keypress(function(e) {
        var code = e.keyCode || e.which;
        if (code == 13) {
            text = $('#text').val();
            $('#text').val('');
            socket.emit('text', {
                msg: text
            });
        }
        cts = getTimestampInSeconds()
        if (LAST_TYPING_TS + 2 < cts) {
            LAST_TYPING_TS = cts;
            socket.emit("typing", { 'player': PLAYER });
        }
    });
});

function leave_room() {
    socket.emit('left', {}, function() {
        socket.disconnect();
    });
}