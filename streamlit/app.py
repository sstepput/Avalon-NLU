import streamlit as st
import pandas as pd
import json
import numpy as np
import plotly.graph_objects as go

DATAFILE = "./streamlit/sample.json"

@st.cache_data
def loadData(path):
    with open(path, "r") as fh:
        data = json.load(fh)
    return data

def highlight_failed_votes(row):
    styles = np.asarray([None] * len(row))
    cnt_fail = 0
    been_voted = True
    for i in range(1, 7):
        if row[f"P{i}"] == "no":
            cnt_fail += 1
        elif row[f"P{i}"] is None:
            been_voted = False
    if been_voted:
        if cnt_fail >= 3:
            styles[2:8] = 'background-color:#ff000011'
        else:
            styles[2:8] = 'background-color:#00ff0011'
    return styles

def getVoteOutcomes(data):
    quest = st.session_state["quest_select"]
    rnd = st.session_state["turn_select"]
    parties = []
    for mid, msg in data["messages"].items():
        if msg["player"] != "system":
            continue
        # Break at the point we want
        if not (msg["quest"] < quest or (msg["quest"] == quest and msg["turn"] <= rnd)):
            break
        if "proposed a party:" in msg["msg"]:
            party = msg["msg"].split("proposed a party: ")[-1].split(",")
            party = [s.replace("player", "plr") for s in party]
            parties.append([msg["quest"],party, None, None, None, None, None, None, None])
        if "party vote outcome:" in  msg["msg"]:
            votes = msg["msg"][20:].split(",")
            for vid, v in enumerate(votes):
                parties[-1][vid+2] = v.split(": ")[-1]
        if "quest succeed" in msg["msg"]:
            parties[-1][-1] = "Success"
        if "quest fail" in msg["msg"]:
            parties[-1][-1] = "Failure"

    # Turn it into a dataframe
    for vote in parties:
        pass
    df = pd.DataFrame(parties, columns=["Quest","The History of Proposed Parties ", "P1", "P2", "P3", "P4", "P5", "P6", "Quest Vote"])

    df = df.style.apply(highlight_failed_votes, axis=1)

    return df

def getNumQuests(data):
    turns = 0
    for mid, msg in data["messages"].items():
        turns = max(turns, msg["quest"])
    return turns

def getNumTurns(data):
    turns = 0
    for mid, msg in data["messages"].items():
        if msg["quest"] != st.session_state["quest_select"]:
            continue
        turns = max(turns, msg["turn"])
    return turns

def local_css(file_name):
    with open(file_name) as f:
        st.markdown('<style>{}</style>'.format(f.read()), unsafe_allow_html=True)

def addChatMessage(player, role, msg, p_strat, d_strat=None, avatar=None):
    with st.chat_message(player, avatar=avatar):
        strategy = f"{p_strat}"
        if d_strat:
            strategy += f" ; {d_strat}"
        st.markdown(f"<div class='player_name'><b>{player}</b> ({role}): <i>{strategy}</i></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='chat_msg'>{msg}</div>", unsafe_allow_html=True)
 
def _getUserRoles(data):
    roles = {}
    for uid, user in data["users"].items():
        roles[user["name"]] = user["role"].split("-")[0].capitalize()
    return roles

def _getMessagePStrat(data, mid):
    for pid, strat in data["persuasion"].items():
        if mid == strat["mid"]:
            p_strat = strat["persuasion"].capitalize()
            d_strat = strat["deception"]
            if d_strat:
                d_strat = d_strat.capitalize()
            return p_strat, d_strat
    return "", ""

def getMessages(data):
    roles = _getUserRoles(data)
    msgs = []
    for mid, msg in data["messages"].items():
        quest = st.session_state["quest_select"]
        rnd = st.session_state["turn_select"]
        if msg["quest"] != quest:
            continue
        if msg["turn"] > rnd:
            break

        # Set Role
        role = None
        if msg["player"] in roles:
            role = roles[msg["player"]]
        av = "🤖"

        # Set Icon
        if msg["player"] != "system":
            av = "😈" if role in ["Assassin", "Morgana"] else "😇"

        # Get strategies
        p_strat, d_strat = _getMessagePStrat(data, msg["mid"])
        m_data = {
            "player": msg["player"],
            "role": role,
            "msg": msg["msg"],
            "p_strat": p_strat,
            "d_strat": d_strat,
            "avatar": av,
        }
        msgs.append(m_data)
    return msgs

def persuasion_plot(msgs):
    nameMap = {
        "assertion": "AS",
        "questioning": "QU",
        "suggestion": "SU",
        "agreement": "AG",
        "logical deduction": "LD",
        "compromise/concession": "CC",
        "critique/opposition": "CO", 
        "appeal/defense": "AD"
    }
    categories = ["AS", "QU", "SU", "AG", "LD", "CC", "CO", "AD"]
    counts_good = [0, 0, 0, 0, 0, 0, 0, 0]
    counts_evil = [0, 0, 0, 0, 0, 0, 0, 0]
    for msg in msgs:
        if msg["p_strat"] != "":
            if msg["role"] in ["Assassin", "Morgana"]:
                counts_good[categories.index(nameMap[msg["p_strat"].lower()])] += 1
            else:
                counts_evil[categories.index(nameMap[msg["p_strat"].lower()])] += 1

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=counts_good,
        theta=categories,
        fill='toself',
        name='Good PS',
        fillcolor='rgba(0,0,255,0.2)',
        line_color='rgba(0,0,255,0.5)'
    ))
    fig.add_trace(go.Scatterpolar(
        r=counts_evil,
        theta=categories,
        fill='toself',
        name='Evil PS',
        fillcolor='rgba(255,0,0,0.2)',
        line_color='rgba(255,0,0,0.5)'
    ))

    fig.update_layout(
    polar=dict(
        radialaxis=dict(
        visible=True,
        )),
        showlegend=False
    )
    return fig

def deception_plot(msgs):
    nameMap = {
        "commission": "CO",
        "omission": "OM",
        "influence": "IN"
    }
    categories = ["CO", "OM", "IN"]
    counts_evil = [0, 0, 0, 0, 0, 0, 0, 0]
    for msg in msgs:
        if msg["d_strat"] not in [None, ""]:
            counts_evil[categories.index(nameMap[msg["d_strat"].lower()])] += 1

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=counts_evil,
        theta=categories,
        fill='toself',
        name='Evil PS',
        fillcolor='rgba(255,0,0,0.2)',
        line_color='rgba(255,0,0,0.5)'
    ))

    fig.update_layout(
    polar=dict(
        radialaxis=dict(
            visible=True,
        )),
        showlegend=False
    )
    return fig

def getPlayerBelieves(data):
    beliefs = []
    for i in range(1, 7):
        beliefs.append([f"Player-{i}", None, None, None, None, None, None])
    df = pd.DataFrame(beliefs, columns=["Player","About Player-1", "About Player-2", "About Player-3", "About Player-4", "About Player-5", "About Player-6"])

    quest = st.session_state["quest_select"]
    rnd = st.session_state["turn_select"]

    for bid, bel in data["beliefs"].items(): 
        if not (bel["quest"] < quest or (bel["quest"] == quest and bel["turn"] <= rnd)):
            break
        idx = int(bel["player"].split("-")[-1])-1
        about = "About " + bel["about_player"].capitalize()
        df.loc[idx, about] = bel["belief"].capitalize()

    return df

if "quest_select" not in st.session_state:
    st.session_state["quest_select"] = 1
if "turn_select" not in st.session_state:
    st.session_state["turn_select"] = 0

 # Setup
local_css("./streamlit/style.css")
st.markdown("<style>div[data-testid=\"stChatMessage\"] \{border-style: solid;\}</style>", unsafe_allow_html=True)
data = loadData(DATAFILE)

# Initial Page Layout
st.markdown("## Avalon Game Visualization")
n_rounds = getNumQuests(data)
n_turns = getNumTurns(data)
n_turns = n_turns if n_turns > 1 else 2
st.markdown(f"The selected game has {n_rounds}. Please select the round you would like to investigate!")
col1, col2 = st.columns(spec=[0.5, 0.5])
col1.slider("Select the Quest", 1, n_rounds, key="quest_select")
col2.slider("Select Turn in Quest", 1, n_turns, key="turn_select")

st.markdown("Below shows the proposed parties and respective vote outcomes. \"None\" refers to a party that has not yet been voted for (or was never voted for as the proposal changed before a vote happened)")
st.dataframe(getVoteOutcomes(data), use_container_width=True, hide_index=True)

relevant_messages = getMessages(data)
st.markdown("__Utilization of Persuasion and Deception Strategies__")
st.markdown("- Persuasion strategies (left, red: Evil, blue: Good) are assertion (AS), questioning (QU), suggestion (SU), agreement (AG), logical deduction (LD), compromise/concession (CC), critique/opposition (CO), and appeal/defense (AD).")
st.markdown("- Deception strategies (right) employed by evil players are commission (CO), omission (OM), and influence (IN)")


col1, col2 = st.columns(spec=[0.5, 0.5])
col1.plotly_chart(persuasion_plot(relevant_messages), use_container_width=True)
col2.plotly_chart(deception_plot(relevant_messages), use_container_width=True)

st.markdown("__Player Beliefs__")
st.markdown("The following highlights what each player (first column) believes the role of the other players are.")
st.dataframe(getPlayerBelieves(data), use_container_width=True, hide_index=True)

st.markdown(f"__Chat History for Round {st.session_state['quest_select']}, up to turn {st.session_state['turn_select']}__")
for msg in relevant_messages:
    addChatMessage(**msg)