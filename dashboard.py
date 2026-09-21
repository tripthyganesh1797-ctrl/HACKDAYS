"""
dashboard.py
------------
Streamlit dashboard with Plain English Natural Language Agent Workflow Input.
Run command: python -m streamlit run dashboard.py
"""

import re
import time
import pandas as pd
import streamlit as st
from reservation_manager import run_simulation, make_agents

st.set_page_config(page_title="Runtime Service-Graph Reservation", layout="wide")

st.title("Runtime Service-Graph Reservation for Multi-Agent Systems")
st.caption(
    "A predictive controller that pre-reserves tool, model, and service dependencies "
    "for concurrent agent workflows without over-allocation or starvation."
)

# ---- Sidebar controls ----
st.sidebar.header("Simulation Settings")
ticks = st.sidebar.slider("Simulation length (ticks)", 20, 80, 40)

st.sidebar.subheader("Resource Capacities")
gpu_cap = st.sidebar.slider("GPU slots", 1, 5, 2)
api_cap = st.sidebar.slider("API slots", 1, 8, 3)
db_cap = st.sidebar.slider("DB slots", 1, 10, 5)
img_cap = st.sidebar.slider("IMAGE_MODEL slots", 1, 4, 1)

RESOURCES = {"GPU": gpu_cap, "API": api_cap, "DB": db_cap, "IMAGE_MODEL": img_cap}


def parse_english_agents(text_input, valid_resources):
    """Parses plain English lines into structured agent definitions.
    Example line:
      'Agent 1 arrives at tick 0 and needs GPU for 3 ticks, then DB for 2 ticks, then API for 3 ticks'
    """
    agents = []
    lines = text_input.strip().split("\n")
    agent_counter = 1

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Extract arrival tick (default to 0 if not specified)
        arrival = 0
        arrival_match = re.search(r"arrives?\s+(?:at\s+)?(?:tick\s+)?(\d+)", line, re.IGNORECASE)
        if arrival_match:
            arrival = int(arrival_match.group(1))

        # Extract agent ID or assign automatically
        agent_id_match = re.search(r"^(Agent[-\s]?\d+|[A-Za-z0-9_-]+)", line, re.IGNORECASE)
        if agent_id_match and "arrives" not in agent_id_match.group(1).lower():
            ag_id = agent_id_match.group(1).strip().capitalize()
        else:
            ag_id = f"Agent-{agent_counter}"

        # Match resource mentions and optional durations
        seq = []
        durations = []

        # Find words matching available resources
        resource_pattern = r"\b(" + "|".join(valid_resources.keys()) + r")\b"
        tokens = re.finditer(resource_pattern, line, re.IGNORECASE)

        for match in tokens:
            res_name = match.group(1).upper()
            # Look ahead in text after resource name to find duration (e.g., 'GPU for 3 ticks' or 'GPU (3)')
            post_text = line[match.end(): match.end() + 25]
            duration_match = re.search(r"(?:for|\:|\()?\s*(\d+)\s*(?:ticks?|\))?", post_text, re.IGNORECASE)

            dur = 3  # default duration if unspecified
            if duration_match and duration_match.group(1):
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


# ---- Agent Mode Selection ----
st.sidebar.subheader("Agent Configuration")
agent_mode = st.sidebar.radio(
    "Workflow Source",
    options=["Random Generation", "Plain English Workflows"],
    index=0
)

custom_agents_data = None

if agent_mode == "Random Generation":
    num_agents = st.sidebar.slider("Number of agents", 3, 12, 6)
    seed = st.sidebar.number_input("Random seed", value=42, step=1)
else:
    num_agents = 0
    seed = 42
    
    st.sidebar.markdown("**Type Agent Workflows in Plain English:**")
    
    default_english_text = (
        "Agent-1 arrives at tick 0 and needs GPU for 3 ticks, then DB for 2 ticks, then API for 3 ticks\n"
        "Agent-2 arrives at tick 2 and needs API for 2 ticks, then IMAGE_MODEL for 4 ticks, then DB for 2 ticks\n"
        "Agent-3 arrives at tick 4 and needs GPU for 3 ticks, then IMAGE_MODEL for 3 ticks, then API for 2 ticks, then DB for 3 ticks"
    )

    english_input = st.sidebar.text_area(
        "Workflow Instructions:",
        value=default_english_text,
        height=220
    )

    parsed_custom = parse_english_agents(english_input, RESOURCES)
    
    if parsed_custom:
        custom_agents_data = parsed_custom
        st.sidebar.success(f"Successfully loaded {len(custom_agents_data)} plain English workflows!")
    else:
        st.sidebar.warning("Could not detect resource names (GPU, API, DB, IMAGE_MODEL) in plain text.")


# Run simulation with either random or custom workflows
@st.cache_data
def get_history_custom(resources, custom_data, num_agents, ticks, seed, mode):
    from reservation_manager import ReservationManager, SERVICE_TRANSITIONS
    import json
    
    mgr = ReservationManager(resources)
    if mode == "Random Generation" or not custom_data:
        agents = make_agents(list(resources.keys()), num_agents, ticks, seed)
    else:
        agents = json.loads(json.dumps(custom_data))

    history = []
    for t in range(ticks):
        tick_start_log_len = len(mgr.log)

        # 1. Active agents try current step & soft-reserve next step
        for ag in agents:
            if ag["idx"] >= len(ag["seq"]) or t < ag["arrival"]:
                continue
                
            curr_resource = ag["seq"][ag["idx"]]
            curr_duration = ag["durations"][ag["idx"]]
            
            if ag["id"] not in mgr.holders[curr_resource] and ag["id"] not in mgr.queue[curr_resource]:
                mgr.try_reserve(t, ag["id"], curr_resource, curr_duration)

            # Look ahead and pre-reserve using transition matrix probability
            nxt_idx = ag["idx"] + 1
            if nxt_idx < len(ag["seq"]):
                nxt_resource = ag["seq"][nxt_idx]
                nxt_duration = ag["durations"][nxt_idx]
                
                prob = SERVICE_TRANSITIONS.get(curr_resource, {}).get(nxt_resource, 0.4)
                if prob >= 0.3:
                    mgr.try_reserve(t, ag["id"], nxt_resource, nxt_duration, predicted=True, probability=prob)

        # 2. Advance timers & process queue
        finished = mgr.tick_update(t)

        # 3. Advance completed agents
        for agent_id, resource in finished:
            for ag in agents:
                if ag["id"] == agent_id and ag["idx"] < len(ag["seq"]) and ag["seq"][ag["idx"]] == resource:
                    ag["idx"] += 1
                    break

        history.append({
            "tick": t,
            "resources": mgr.snapshot(),
            "log": mgr.log[tick_start_log_len:],
        })

    return history, agents


history, agents = get_history_custom(
    RESOURCES, custom_agents_data, num_agents, ticks, seed, agent_mode
)

# ---- Tick scrub control ----
if "tick" not in st.session_state:
    st.session_state.tick = 0

col_a, col_b = st.columns([3, 1])
with col_a:
    tick = st.slider("Tick", 0, len(history) - 1, st.session_state.tick, key="tick_slider")
with col_b:
    autoplay = st.checkbox("Autoplay")

st.session_state.tick = tick
snap = history[tick]

# ---- Resource bars ----
st.subheader(f"System Capacity State at Tick {tick}")
cols = st.columns(len(RESOURCES))
for col, (name, info) in zip(cols, snap["resources"].items()):
    with col:
        st.markdown(f"### {name}")
        used = info["used"]
        predicted = info["predicted"]
        cap = info["capacity"]
        
        st.progress(min(1.0, (used + predicted) / cap))
        st.write(f"**Active:** {used}/{cap}")
        st.write(f"**Pre-reserved (Soft):** {predicted}")
        st.write(f"**Queued:** {info['queue_len']}")

st.divider()

# ---- Resource Utilization Trends Line Chart ----
st.subheader("Resource Utilization Trends (Over All Ticks)")

trend_data = []
for h in history:
    t_val = h["tick"]
    row = {"Tick": t_val}
    for r_name, r_info in h["resources"].items():
        row[f"{r_name} Active"] = r_info["used"]
        row[f"{r_name} Pre-Reserved"] = r_info["predicted"]
    trend_data.append(row)

df_trends = pd.DataFrame(trend_data).set_index("Tick")

selected_resources = st.multiselect(
    "Filter resources to chart:",
    options=list(RESOURCES.keys()),
    default=list(RESOURCES.keys()),
)

if selected_resources:
    chart_cols = []
    for r in selected_resources:
        chart_cols.extend([f"{r} Active", f"{r} Pre-Reserved"])
    st.line_chart(df_trends[chart_cols])
else:
    st.info("Select at least one resource above to display trends.")

st.divider()

# ---- Agent Progress Matrix ----
st.subheader("Agent Workflow Pipelines")
agent_table = []
for ag in agents:
    arrival = ag["arrival"]
    status = "Waiting"
    current_tool = "None"
    
    if tick >= arrival:
        if ag["idx"] >= len(ag["seq"]):
            status = "Completed"
            current_tool = "Done"
        else:
            status = "Active"
            current_tool = ag["seq"][ag["idx"]]

    pipeline_str = " ➔ ".join(
        f"**[{s}]**" if (i == ag["idx"] and status == "Active") else s
        for i, s in enumerate(ag["seq"])
    )

    agent_table.append({
        "Agent ID": ag["id"],
        "Arrival Tick": arrival,
        "Status": status,
        "Active Dependency": current_tool,
        "Workflow Graph Step": pipeline_str,
    })

st.dataframe(agent_table, use_container_width=True)

# ---- Controller Stats ----
st.subheader("Controller Performance Metrics")
total_queued = sum(
    1 for s in history[: tick + 1] for _, line in s["log"] if "QUEUED" in line
)
total_predicted = sum(
    1 for s in history[: tick + 1] for _, line in s["log"] if "pre-reserved" in line and "CONFIRMED" not in line
)
total_confirmed = sum(
    1 for s in history[: tick + 1] for _, line in s["log"] if "CONFIRMED" in line
)

c1, c2, c3 = st.columns(3)
c1.metric("Starvation Events Prevented (FIFO Queueing)", total_queued)
c2.metric("Predictive Pre-Reservations Issued", total_predicted)
c3.metric("Confirmed Predictions Used", total_confirmed)

# ---- Event log ----
st.subheader("System Event Log")
log_lines = []
for s in history[: tick + 1]:
    for t_, line in s["log"]:
        log_lines.append(f"[t={t_}] {line}")

st.text_area("Event Stream", value="\n".join(log_lines[-200:]), height=250)

if autoplay and tick < len(history) - 1:
    time.sleep(0.3)
    st.session_state.tick = tick + 1
    st.rerun()