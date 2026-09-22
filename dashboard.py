"""
dashboard.py

Streamlit dashboard with:

1. Plain English Natural Language Agent Workflow Input.
2. Fragment-based Play / Pause / Restart Autoplay.
3. Interactive Service-Graph DAG Visualizer.
4. Real-time Plotly Gantt Execution Timeline.
5. Clickable Agent Details Popup.
6. Capacity Gauges, Trend Charts, and Event Stream.
7. Internet Connectivity Detection.
8. 60-second Offline Grace Period.
9. Automatic Resume When Internet Returns.

Run command:

python -m streamlit run dashboard.py
"""

import re
import json
import socket
import time

import pandas as pd
import plotly.express as px
import streamlit as st

from reservation_manager import (
    ReservationManager,
    SERVICE_TRANSITIONS,
    make_agents,
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Runtime Service-Graph Reservation",
    layout="wide"
)

st.title("Runtime Service-Graph Reservation for Multi-Agent Systems")

st.caption(
    "A predictive controller that pre-reserves tool, model, and service "
    "dependencies for concurrent agent workflows without over-allocation "
    "or starvation."
)


# ============================================================
# NETWORK / OFFLINE CONFIGURATION
# ============================================================

OFFLINE_GRACE_SECONDS = 60

# We don't check the internet every 0.5 seconds.
# Instead, we check approximately every 5 seconds.
NETWORK_CHECK_INTERVAL = 5


def check_internet_connection():
    """
    Check whether the machine currently has external
    network/internet connectivity.

    This does NOT affect the simulation itself.
    """

    test_hosts = [
        ("1.1.1.1", 53),
        ("8.8.8.8", 53)
    ]

    for host, port in test_hosts:

        try:

            sock = socket.create_connection(
                (host, port),
                timeout=0.7
            )

            sock.close()

            return True

        except OSError:
            continue

    return False


# ============================================================
# NETWORK SESSION STATE
# ============================================================

if "network_status" not in st.session_state:
    st.session_state.network_status = True

if "last_network_check" not in st.session_state:
    st.session_state.last_network_check = 0.0

if "offline_started_at" not in st.session_state:
    st.session_state.offline_started_at = None

if "offline_pause_triggered" not in st.session_state:
    st.session_state.offline_pause_triggered = False

if "was_playing_before_offline" not in st.session_state:
    st.session_state.was_playing_before_offline = False


def update_network_status():
    """
    Update network state without checking the network
    on every 0.5 second fragment rerun.
    """

    now = time.monotonic()

    if (
        now - st.session_state.last_network_check
        >= NETWORK_CHECK_INTERVAL
    ):

        previous_status = st.session_state.network_status

        current_status = check_internet_connection()

        st.session_state.network_status = current_status

        st.session_state.last_network_check = now

        # ====================================================
        # INTERNET JUST WENT OFFLINE
        # ====================================================

        if previous_status and not current_status:

            st.session_state.offline_started_at = now

            st.session_state.was_playing_before_offline = (
                st.session_state.get("playing", False)
            )

            st.session_state.offline_pause_triggered = False

        # ====================================================
        # INTERNET CAME BACK
        # ====================================================

        elif not previous_status and current_status:

            st.session_state.offline_started_at = None

            # Resume only if the simulation was running
            # before the connection disappeared.

            if st.session_state.was_playing_before_offline:

                st.session_state.playing = True

            st.session_state.offline_pause_triggered = False

            st.session_state.was_playing_before_offline = False


update_network_status()


# ============================================================
# SIDEBAR CONTROLS
# ============================================================

st.sidebar.header("Simulation Settings")

ticks = st.sidebar.slider(
    "Simulation length (ticks)",
    20,
    80,
    40
)

st.sidebar.subheader("Resource Capacities")

gpu_cap = st.sidebar.slider(
    "GPU slots",
    1,
    5,
    2
)

api_cap = st.sidebar.slider(
    "API slots",
    1,
    8,
    3
)

db_cap = st.sidebar.slider(
    "DB slots",
    1,
    10,
    5
)

img_cap = st.sidebar.slider(
    "IMAGE_MODEL slots",
    1,
    4,
    1
)


# ============================================================
# RESOURCE DEFINITIONS
# ============================================================

RESOURCES = {
    "GPU": gpu_cap,
    "API": api_cap,
    "DB": db_cap,
    "IMAGE_MODEL": img_cap
}


# ============================================================
# PLAIN ENGLISH AGENT PARSER
# ============================================================

def parse_english_agents(text_input, valid_resources):

    agents = []

    lines = text_input.strip().split("\n")

    agent_counter = 1

    for line in lines:

        line = line.strip()

        if not line or line.startswith("#"):
            continue

        # ----------------------------------------------------
        # Arrival tick
        # ----------------------------------------------------

        arrival = 0

        arrival_match = re.search(
            r"arrives?\s+(?:at\s+)?(?:tick\s+)?(\d+)",
            line,
            re.IGNORECASE
        )

        if arrival_match:
            arrival = int(arrival_match.group(1))

        # ----------------------------------------------------
        # Agent ID
        # ----------------------------------------------------

        agent_id_match = re.search(
            r"^(Agent[-\s]?\d+|[A-Za-z0-9_-]+)",
            line,
            re.IGNORECASE
        )

        if (
            agent_id_match
            and "arrives" not in agent_id_match.group(1).lower()
        ):

            ag_id = agent_id_match.group(1).strip()

            if ag_id.lower().startswith("agent"):

                parts = re.split(
                    r"[-\s]+",
                    ag_id
                )

                if len(parts) > 1:
                    ag_id = f"Agent-{parts[-1]}"

                else:
                    ag_id = ag_id.capitalize()

        else:

            ag_id = f"Agent-{agent_counter}"

        # ----------------------------------------------------
        # Resources and durations
        # ----------------------------------------------------

        seq = []
        durations = []

        resource_pattern = (
            r"\b("
            + "|".join(
                re.escape(r)
                for r in valid_resources.keys()
            )
            + r")\b"
        )

        tokens = re.finditer(
            resource_pattern,
            line,
            re.IGNORECASE
        )

        for match in tokens:

            res_name = match.group(1).upper()

            post_text = line[
                match.end():
                match.end() + 40
            ]

            duration_match = re.search(
                r"(?:for|:)?\s*(\d+)\s*(?:ticks?)?",
                post_text,
                re.IGNORECASE
            )

            dur = 3

            if duration_match:
                dur = int(duration_match.group(1))

            seq.append(res_name)

            durations.append(dur)

        if seq:

            agents.append({
                "id": ag_id,
                "arrival": arrival,
                "seq": seq,
                "durations": durations,
                "idx": 0
            })

            agent_counter += 1

    return agents


# ============================================================
# AGENT MODE
# ============================================================

st.sidebar.subheader("Agent Configuration")

agent_mode = st.sidebar.radio(
    "Workflow Source",
    options=[
        "Random Generation",
        "Plain English Workflows"
    ],
    index=0
)

custom_agents_data = None


if agent_mode == "Random Generation":

    num_agents = st.sidebar.slider(
        "Number of agents",
        3,
        12,
        6
    )

    seed = st.sidebar.number_input(
        "Random seed",
        value=42,
        step=1
    )

else:

    num_agents = 0
    seed = 42

    st.sidebar.markdown(
        "**Type Agent Workflows in Plain English:**"
    )

    default_english_text = (
        "Agent-1 arrives at tick 0 and needs GPU for 3 ticks, "
        "then DB for 2 ticks, then API for 3 ticks\n"
        "Agent-2 arrives at tick 2 and needs API for 2 ticks, "
        "then IMAGE_MODEL for 4 ticks, then DB for 2 ticks\n"
        "Agent-3 arrives at tick 4 and needs GPU for 3 ticks, "
        "then IMAGE_MODEL for 3 ticks, then API for 2 ticks, "
        "then DB for 3 ticks"
    )

    english_input = st.sidebar.text_area(
        "Workflow Instructions:",
        value=default_english_text,
        height=200
    )

    parsed_custom = parse_english_agents(
        english_input,
        RESOURCES
    )

    if parsed_custom:

        custom_agents_data = parsed_custom

        st.sidebar.success(
            f"Loaded {len(custom_agents_data)} "
            "plain English workflows!"
        )

    else:

        st.sidebar.warning(
            "Could not detect valid resource names "
            "(GPU, API, DB, IMAGE_MODEL)."
        )


# ============================================================
# SIMULATION WITH GANTT RECORDING
# ============================================================

@st.cache_data
def get_history_custom(
    resources,
    custom_data,
    num_agents,
    ticks,
    seed,
    mode
):

    mgr = ReservationManager(resources)

    # --------------------------------------------------------
    # Create agents
    # --------------------------------------------------------

    if mode == "Random Generation" or not custom_data:

        agents = make_agents(
            list(resources.keys()),
            num_agents,
            ticks,
            seed
        )

    else:

        agents = json.loads(
            json.dumps(custom_data)
        )

    history = []
    gantt_records = []

    # ========================================================
    # SIMULATION LOOP
    # ========================================================

    for t in range(ticks):

        tick_start_log_len = len(mgr.log)

        # ----------------------------------------------------
        # 1. Process active agents and predictive reservations
        # ----------------------------------------------------

        for ag in agents:

            if (
                ag["idx"] >= len(ag["seq"])
                or t < ag["arrival"]
            ):
                continue

            curr_resource = ag["seq"][ag["idx"]]
            curr_duration = ag["durations"][ag["idx"]]

            # ------------------------------------------------
            # Real reservation
            # ------------------------------------------------

            if (
                ag["id"] not in mgr.holders[curr_resource]
                and ag["id"] not in mgr.queue[curr_resource]
            ):

                granted = mgr.try_reserve(
                    t,
                    ag["id"],
                    curr_resource,
                    curr_duration
                )

                if granted:

                    gantt_records.append({
                        "Agent": ag["id"],
                        "Resource": curr_resource,
                        "Start": t,
                        "Finish": t + curr_duration,
                        "Duration": curr_duration,
                        "Step": (
                            f"Step {ag['idx'] + 1} "
                            f"({curr_resource})"
                        )
                    })

            # ------------------------------------------------
            # Look ahead and pre-reserve
            # ------------------------------------------------

            nxt_idx = ag["idx"] + 1

            if nxt_idx < len(ag["seq"]):

                nxt_resource = ag["seq"][nxt_idx]

                nxt_duration = ag["durations"][nxt_idx]

                prob = SERVICE_TRANSITIONS.get(
                    curr_resource,
                    {}
                ).get(
                    nxt_resource,
                    0.4
                )

                if prob >= 0.3:

                    mgr.try_reserve(
                        t,
                        ag["id"],
                        nxt_resource,
                        nxt_duration,
                        predicted=True,
                        probability=prob
                    )

        # ----------------------------------------------------
        # 2. Advance timers and process queue
        # ----------------------------------------------------

        finished_steps, newly_granted = mgr.tick_update(t)

        # ----------------------------------------------------
        # Log newly unblocked agents into Gantt
        # ----------------------------------------------------

        for nxt_agent, resource, duration in newly_granted:

            ag_match = next(
                (
                    a
                    for a in agents
                    if a["id"] == nxt_agent
                ),
                None
            )

            if ag_match:

                step_label = (
                    f"Step {ag_match['idx'] + 1} "
                    f"({resource})"
                )

            else:

                step_label = (
                    f"Dispatched ({resource})"
                )

            gantt_records.append({
                "Agent": nxt_agent,
                "Resource": resource,
                "Start": t,
                "Finish": t + duration,
                "Duration": duration,
                "Step": step_label
            })

        # ----------------------------------------------------
        # 3. Advance completed agents
        # ----------------------------------------------------

        for agent_id, resource in finished_steps:

            for ag in agents:

                if (
                    ag["id"] == agent_id
                    and ag["idx"] < len(ag["seq"])
                    and ag["seq"][ag["idx"]] == resource
                ):

                    ag["idx"] += 1

                    break

        # ----------------------------------------------------
        # Save history
        # ----------------------------------------------------

        history.append({
            "tick": t,
            "resources": mgr.snapshot(),
            "log": mgr.log[
                tick_start_log_len:
            ]
        })

    return history, agents, gantt_records


# ============================================================
# RUN SIMULATION
# ============================================================

history, agents, gantt_records = get_history_custom(
    RESOURCES,
    custom_agents_data,
    num_agents,
    ticks,
    seed,
    agent_mode
)


# ============================================================
# SIMULATION CONTROLS
# ============================================================

if "tick" not in st.session_state:
    st.session_state.tick = 0

if "playing" not in st.session_state:
    st.session_state.playing = False

if "last_agent_selection" not in st.session_state:
    st.session_state.last_agent_selection = None


# ============================================================
# NETWORK STATUS DISPLAY
# ============================================================

if st.session_state.network_status:

    st.success(
        "🟢 ONLINE — Network connection available"
    )

else:

    if st.session_state.offline_started_at is not None:

        elapsed_offline = (
            time.monotonic()
            - st.session_state.offline_started_at
        )

        remaining_offline = max(
            0,
            int(
                OFFLINE_GRACE_SECONDS
                - elapsed_offline
            )
        )

    else:

        remaining_offline = OFFLINE_GRACE_SECONDS

    if remaining_offline > 0:

        st.warning(
            f"🟠 OFFLINE MODE — "
            f"Simulation continues locally. "
            f"{remaining_offline} seconds remaining."
        )

    else:

        st.error(
            "🔴 OFFLINE — "
            "60-second offline grace period expired."
        )


# ============================================================
# SIMULATION CONTROLS
# ============================================================

st.subheader("Simulation Controls")

col1, col2, col3 = st.columns(3)


with col1:

    if st.button(
        "▶ PLAY",
        use_container_width=True
    ):

        st.session_state.playing = True

        st.rerun()


with col2:

    if st.button(
        "⏸ STOP",
        use_container_width=True
    ):

        st.session_state.playing = False

        st.rerun()


with col3:

    if st.button(
        "↺ RESTART",
        use_container_width=True
    ):

        st.session_state.tick = 0

        st.session_state.playing = False

        st.session_state.last_agent_selection = None

        st.rerun()


# ============================================================
# AGENT DETAILS DIALOG
# ============================================================

@st.dialog("🤖 Agent Details")
def show_agent_details(agent_id, agent_list):

    # --------------------------------------------------------
    # Find selected agent
    # --------------------------------------------------------

    selected_agent = next(
        (
            ag
            for ag in agent_list
            if ag["id"] == agent_id
        ),
        None
    )

    # --------------------------------------------------------
    # Find execution records
    # --------------------------------------------------------

    agent_records = [
        record
        for record in gantt_records
        if record["Agent"] == agent_id
    ]

    agent_data = pd.DataFrame(agent_records)

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    st.subheader(
        f"🤖 {agent_id}"
    )

    if selected_agent is not None:

        arrival = selected_agent["arrival"]

        workflow = selected_agent["seq"]

        st.write(
            f"📥 **Arrival:** Tick {arrival}"
        )

        st.write(
            f"🔄 **Workflow steps:** "
            f"{len(workflow)}"
        )

    if agent_data.empty:

        st.warning(
            "This agent has not started executing yet."
        )

        if selected_agent is not None:

            workflow_text = " → ".join(
                selected_agent["seq"]
            )

            st.info(
                f"Planned workflow: **{workflow_text}**"
            )

        return

    # ========================================================
    # SIMPLE ENGLISH SUMMARY
    # ========================================================

    st.markdown(
        "### 💬 What is this agent doing?"
    )

    workflow_text = " → ".join(
        agent_data["Resource"].astype(str)
    )

    st.success(
        f"**{agent_id}** is executing the workflow: "
        f"**{workflow_text}**."
    )

    # ========================================================
    # EXECUTION SUMMARY
    # ========================================================

    st.markdown(
        "### 📊 Execution Summary"
    )

    first_tick = int(
        agent_data["Start"].min()
    )

    last_tick = int(
        agent_data["Finish"].max()
    )

    total_duration = int(
        agent_data["Duration"].sum()
    )

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Started",
        f"Tick {first_tick}"
    )

    m2.metric(
        "Last Tick",
        f"Tick {last_tick}"
    )

    m3.metric(
        "Total Duration",
        f"{total_duration} ticks"
    )

    # ========================================================
    # STEP-BY-STEP EXPLANATION
    # ========================================================

    st.markdown(
        "### 🔄 Step-by-Step Workflow"
    )

    for i, (_, row) in enumerate(
        agent_data.iterrows(),
        start=1
    ):

        resource = row["Resource"]

        start = int(row["Start"])

        finish = int(row["Finish"])

        duration = int(row["Duration"])

        st.markdown(
            f"""
**Step {i}: {resource}**

The agent uses **{resource}** from
**tick {start} → tick {finish}**.

⏱️ Duration: **{duration} ticks**
"""
        )

    # ========================================================
    # RESOURCES USED
    # ========================================================

    st.markdown(
        "### 📦 Resources Used"
    )

    resource_counts = (
        agent_data["Resource"]
        .value_counts()
    )

    for resource, count in resource_counts.items():

        st.write(
            f"• **{resource}** — used "
            f"{count} time(s)"
        )

    # ========================================================
    # CURRENT WORKFLOW
    # ========================================================

    if selected_agent is not None:

        st.markdown(
            "### 📍 Current Agent Status"
        )

        idx = selected_agent["idx"]

        sequence = selected_agent["seq"]

        if idx >= len(sequence):

            st.success(
                "✅ This agent has completed "
                "its workflow."
            )

        else:

            current_resource = sequence[idx]

            st.info(
                f"🔵 Current workflow resource: "
                f"**{current_resource}**"
            )

            remaining = sequence[idx:]

            remaining_text = " → ".join(
                remaining
            )

            st.write(
                f"Remaining workflow: "
                f"**{remaining_text}**"
            )

    # ========================================================
    # CONTROLLER EXPLANATION
    # ========================================================

    st.markdown(
        "### 🧠 How the Reservation Controller Helps"
    )

    st.write(
        "The controller looks at the agent's current "
        "resource and predicts what resource it may "
        "need next."
    )

    st.write(
        "If the predicted transition has sufficient "
        "probability, the system can create a soft "
        "pre-reservation for that future resource."
    )

    st.info(
        "💡 This helps reduce the chance that an agent "
        "gets blocked when it moves to its next "
        "dependency."
    )


# ============================================================
# LIVE SIMULATION FRAGMENT
# ============================================================

@st.fragment(run_every=0.5)
def simulation_view():

    # ========================================================
    # UPDATE NETWORK STATUS
    # ========================================================

    update_network_status()

    # ========================================================
    # OFFLINE TIMER
    # ========================================================

    if not st.session_state.network_status:

        if st.session_state.offline_started_at is None:

            st.session_state.offline_started_at = (
                time.monotonic()
            )

        offline_elapsed = (
            time.monotonic()
            - st.session_state.offline_started_at
        )

        offline_remaining = (
            OFFLINE_GRACE_SECONDS
            - offline_elapsed
        )

        # ----------------------------------------------------
        # Still inside 60-second offline window
        # ----------------------------------------------------

        if offline_remaining > 0:

            st.warning(
                f"🟠 OFFLINE MODE — "
                f"Simulation is running locally. "
                f"{int(offline_remaining)} seconds remaining."
            )

        # ----------------------------------------------------
        # Offline period expired
        # ----------------------------------------------------

        else:

            if (
                st.session_state.playing
                and not st.session_state.offline_pause_triggered
            ):

                st.session_state.playing = False

                st.session_state.offline_pause_triggered = True

                st.error(
                    "🔴 OFFLINE LIMIT REACHED — "
                    "Simulation paused after 60 seconds."
                )

    # ========================================================
    # PLAYBACK
    # ========================================================

    if st.session_state.playing:

        if st.session_state.tick < len(history) - 1:

            st.session_state.tick += 1

        else:

            st.session_state.playing = False

    tick = st.session_state.tick

    snap = history[tick]

    # ========================================================
    # PLAYBACK STATUS
    # ========================================================

    if st.session_state.network_status:

        if st.session_state.playing:

            st.success(
                f"▶ PLAYING — Tick {tick} / "
                f"{len(history) - 1}"
            )

            st.progress(
                tick / (len(history) - 1)
            )

        else:

            if tick == len(history) - 1:

                st.success(
                    f"✓ SIMULATION COMPLETED — "
                    f"Tick {tick} / {len(history) - 1}"
                )

            else:

                st.info(
                    f"⏸ PAUSED — Tick {tick} / "
                    f"{len(history) - 1}"
                )

    else:

        if st.session_state.playing:

            st.warning(
                f"🟠 OFFLINE PLAYING — Tick "
                f"{tick} / {len(history) - 1}"
            )

            if (
                st.session_state.offline_started_at
                is not None
            ):

                elapsed = (
                    time.monotonic()
                    - st.session_state.offline_started_at
                )

                remaining = max(
                    0,
                    int(
                        OFFLINE_GRACE_SECONDS
                        - elapsed
                    )
                )

                st.progress(
                    remaining
                    / OFFLINE_GRACE_SECONDS
                )

        else:

            st.warning(
                f"⏸ OFFLINE / PAUSED — Tick "
                f"{tick} / {len(history) - 1}"
            )

    # ========================================================
    # SCRUB SLIDER
    # ========================================================

    if not st.session_state.playing:

        selected_tick = st.slider(
            "Simulation Tick",
            min_value=0,
            max_value=len(history) - 1,
            value=st.session_state.tick,
            key="manual_tick"
        )

        if selected_tick != st.session_state.tick:

            st.session_state.tick = selected_tick

            st.rerun()

    else:

        st.write(
            f"**Current Progress: Tick "
            f"{tick} / {len(history) - 1}**"
        )

    # ========================================================
    # RESOURCE STATE GAUGES
    # ========================================================

    st.subheader(
        f"System Capacity State at Tick {tick}"
    )

    cols = st.columns(
        len(RESOURCES)
    )

    for col, (name, info) in zip(
        cols,
        snap["resources"].items()
    ):

        with col:

            st.markdown(
                f"### {name}"
            )

            used = info["used"]

            predicted = info["predicted"]

            cap = info["capacity"]

            st.progress(
                min(
                    1.0,
                    (used + predicted) / cap
                )
            )

            st.write(
                f"**Active:** {used}/{cap}"
            )

            st.write(
                f"**Pre-reserved (Soft):** "
                f"{predicted}"
            )

            st.write(
                f"**Queued:** "
                f"{info['queue_len']}"
            )

    st.divider()

    # ========================================================
    # TABS
    # ========================================================

    (
        tab_gantt,
        tab_dag,
        tab_trends,
        tab_agents,
        tab_logs
    ) = st.tabs([
        "Execution Timeline (Gantt)",
        "Service-Graph DAG",
        "Resource Trends",
        "Agent Pipelines",
        "Event Log & Metrics"
    ])

    # ========================================================
    # 1. GANTT TIMELINE
    # ========================================================

    with tab_gantt:

        st.subheader(
            "Agent Execution Timeline (Gantt Chart)"
        )

        st.caption(
            "Click an agent's execution bar to "
            "view its workflow details."
        )

        if gantt_records:

            df_gantt = pd.DataFrame(
                gantt_records
            )

            df_visible = df_gantt[
                df_gantt["Start"] <= tick
            ].copy()

            if not df_visible.empty:

                df_visible[
                    "Clamped_Finish"
                ] = df_visible[
                    "Finish"
                ].apply(
                    lambda f: min(f, tick + 1)
                )

                # ------------------------------------------------
                # CREATE GANTT
                # ------------------------------------------------

                fig = px.timeline(
                    df_visible,

                    x_start=pd.to_datetime(
                        df_visible["Start"],
                        unit="s"
                    ),

                    x_end=pd.to_datetime(
                        df_visible["Clamped_Finish"],
                        unit="s"
                    ),

                    y="Agent",

                    color="Resource",

                    custom_data=[
                        "Agent",
                        "Resource",
                        "Step",
                        "Duration"
                    ],

                    hover_data=[
                        "Step",
                        "Duration"
                    ],

                    color_discrete_map={
                        "GPU": "#EF553B",
                        "API": "#FFA15A",
                        "DB": "#00CC96",
                        "IMAGE_MODEL": "#AB63FA"
                    }
                )

                fig.update_yaxes(
                    autorange="reversed"
                )

                fig.update_layout(
                    xaxis_title=(
                        f"Simulation Progression "
                        f"(Ticks 0 to {tick})"
                    ),

                    yaxis_title="Agent ID",

                    height=340,

                    xaxis=dict(
                        tickformat="%S"
                    ),

                    clickmode="event+select"
                )

                # ------------------------------------------------
                # INTERACTIVE PLOTLY CHART
                # ------------------------------------------------

                event = st.plotly_chart(
                    fig,
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="points"
                )

                # =================================================
                # DETECT CLICKED AGENT
                # =================================================

                if (
                    event
                    and event.selection
                    and event.selection.points
                ):

                    clicked_point = (
                        event.selection.points[0]
                    )

                    custom_data = (
                        clicked_point.get(
                            "customdata"
                        )
                    )

                    if custom_data:

                        agent_id = custom_data[0]

                        selection_id = (
                            agent_id,
                            custom_data[1],
                            custom_data[2]
                        )

                        if (
                            st.session_state.get(
                                "last_agent_selection"
                            )
                            != selection_id
                        ):

                            st.session_state.last_agent_selection = (
                                selection_id
                            )

                            show_agent_details(
                                agent_id,
                                agents
                            )

            else:

                st.info(
                    "No agents have begun "
                    "resource execution at this tick."
                )

        else:

            st.info(
                "No execution data available."
            )

    # ========================================================
    # 2. SERVICE-GRAPH DAG TAB
    # ========================================================

    with tab_dag:

        st.subheader(
            "Probabilistic Service-Graph Topology "
            "(Markov Chain)"
        )

        st.caption(
            "Directed transition dependencies and "
            "conditional probabilities "
            "P(Next Tool | Current Tool)."
        )

        dot_str = (
            'digraph ServiceDAG {\n'
            '  rankdir=LR;\n'
            '  bgcolor="transparent";\n'
        )

        dot_str += (
            '  node [style="filled,rounded", '
            'shape=box, '
            'fillcolor="#F0F2F6", '
            'fontname="Sans-Serif", '
            'color="#D1D5DB"];\n'
        )

        dot_str += (
            '  edge [fontname="Sans-Serif", '
            'color="#64748B"];\n'
        )

        # --------------------------------------------------------
        # Nodes
        # --------------------------------------------------------

        for res_name, cap_val in RESOURCES.items():

            active_now = snap[
                "resources"
            ][res_name]["used"]

            soft_now = snap[
                "resources"
            ][res_name]["predicted"]

            dot_str += (
                f'  "{res_name}" '
                f'[label="{res_name}\\n'
                f'(Cap: {cap_val} | '
                f'Active: {active_now} | '
                f'Soft: {soft_now})"];\n'
            )

        # --------------------------------------------------------
        # Edges
        # --------------------------------------------------------

        for src, transitions in (
            SERVICE_TRANSITIONS.items()
        ):

            for dst, prob in (
                transitions.items()
            ):

                if prob > 0:

                    dot_str += (
                        f'  "{src}" -> "{dst}" '
                        f'[label=" P={prob:.0%}", '
                        f'fontcolor="#2563EB"];\n'
                    )

        dot_str += "}"

        st.graphviz_chart(
            dot_str
        )

    # ========================================================
    # 3. RESOURCE TRENDS TAB
    # ========================================================

    with tab_trends:

        st.subheader(
            "Resource Utilization Trends "
            "(Over All Ticks)"
        )

        trend_data = []

        for h in history:

            row = {
                "Tick": h["tick"]
            }

            for (
                r_name,
                r_info
            ) in h["resources"].items():

                row[
                    f"{r_name} Active"
                ] = r_info["used"]

                row[
                    f"{r_name} Pre-Reserved"
                ] = r_info["predicted"]

            trend_data.append(row)

        df_trends = pd.DataFrame(
            trend_data
        ).set_index("Tick")

        selected_resources = st.multiselect(
            "Filter resources to chart:",

            options=list(
                RESOURCES.keys()
            ),

            default=list(
                RESOURCES.keys()
            ),

            key="trend_filter"
        )

        if selected_resources:

            chart_cols = []

            for r in selected_resources:

                chart_cols.extend([
                    f"{r} Active",
                    f"{r} Pre-Reserved"
                ])

            st.line_chart(
                df_trends[chart_cols]
            )

        else:

            st.info(
                "Select at least one resource "
                "above to display trends."
            )

    # ========================================================
    # 4. AGENT PIPELINES TAB
    # ========================================================

    with tab_agents:

        st.subheader(
            "Agent Workflow Pipelines"
        )

        agent_table = []

        for ag in agents:

            arrival = ag["arrival"]

            status = "Waiting"

            current_tool = "None"

            if tick >= arrival:

                if (
                    ag["idx"]
                    >= len(ag["seq"])
                ):

                    status = "Completed"

                    current_tool = "Done"

                else:

                    status = "Active"

                    current_tool = (
                        ag["seq"][ag["idx"]]
                    )

            pipeline_str = " ➔ ".join(
                (
                    f"**[{s}]**"
                    if (
                        i == ag["idx"]
                        and status == "Active"
                    )
                    else s
                )

                for i, s in enumerate(
                    ag["seq"]
                )
            )

            agent_table.append({
                "Agent ID": ag["id"],
                "Arrival Tick": arrival,
                "Status": status,
                "Active Dependency": current_tool,
                "Workflow Graph Step": pipeline_str
            })

        st.dataframe(
            agent_table,
            use_container_width=True
        )

    # ========================================================
    # 5. METRICS & LOGS TAB
    # ========================================================

    with tab_logs:

        st.subheader(
            "Controller Performance Metrics"
        )

        total_queued = sum(
            1
            for s in history[:tick + 1]
            for _, line in s["log"]
            if "QUEUED" in line
        )

        total_predicted = sum(
            1
            for s in history[:tick + 1]
            for _, line in s["log"]
            if (
                "pre-reserved" in line
                and "CONFIRMED" not in line
            )
        )

        total_confirmed = sum(
            1
            for s in history[:tick + 1]
            for _, line in s["log"]
            if "CONFIRMED" in line
        )

        total_preemptions = sum(
            1
            for s in history[:tick + 1]
            for _, line in s["log"]
            if "preempted" in line
        )

        m1, m2, m3, m4 = st.columns(4)

        m1.metric(
            "Queued Requests",
            total_queued
        )

        m2.metric(
            "Pre-Reservations Issued",
            total_predicted
        )

        m3.metric(
            "Confirmed Predictions",
            total_confirmed
        )

        m4.metric(
            "Speculative Preemptions",
            total_preemptions
        )

        st.subheader(
            "System Event Stream"
        )

        log_lines = []

        for s in history[:tick + 1]:

            for t_value, line in s["log"]:

                log_lines.append(
                    f"[t={t_value}] {line}"
                )

        st.text_area(
            "Live Event Stream",

            value="\n".join(
                log_lines[-200:]
            ),

            height=250
        )


# ============================================================
# RUN SIMULATION VIEW
# ============================================================

simulation_view()