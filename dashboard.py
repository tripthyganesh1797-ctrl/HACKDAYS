"""
dashboard.py
------------
Streamlit dashboard for the hackathon demo.

Why "scrub through a slider" instead of live/real-time updates?
Because live async updates in Streamlit are fragile and easy to break right
before a demo. Instead, we run the WHOLE simulation once (instant), store
every tick's state, and let you scrub/play through it with a slider. It looks
just as "live" to judges, but can never crash mid-demo.

To run:  streamlit run dashboard.py
"""

import time
import streamlit as st
from reservation_manager import run_simulation

st.set_page_config(page_title="Runtime Service-Graph Reservation", layout="wide")

st.title("Runtime Service-Graph Reservation for Multi-Agent Systems")
st.caption(
    "A controller that predicts upcoming resource needs of concurrent agent "
    "workflows and pre-reserves them - without over-allocation or starvation."
)

# ---- Sidebar controls ----
st.sidebar.header("Simulation settings")
num_agents = st.sidebar.slider("Number of agents", 3, 12, 6)
ticks = st.sidebar.slider("Simulation length (ticks)", 20, 80, 40)
seed = st.sidebar.number_input("Random seed", value=42, step=1)

st.sidebar.subheader("Resource capacities")
gpu_cap = st.sidebar.slider("GPU slots", 1, 5, 2)
api_cap = st.sidebar.slider("API slots", 1, 8, 3)
db_cap = st.sidebar.slider("DB slots", 1, 10, 5)
img_cap = st.sidebar.slider("IMAGE_MODEL slots", 1, 4, 1)

RESOURCES = {"GPU": gpu_cap, "API": api_cap, "DB": db_cap, "IMAGE_MODEL": img_cap}

# Re-run simulation only when settings change (cached for speed)
@st.cache_data
def get_history(resources, num_agents, ticks, seed):
    return run_simulation(resources, num_agents=num_agents, ticks=ticks, seed=seed)

history, agents = get_history(RESOURCES, num_agents, ticks, seed)

# ---- Tick control ----
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
st.subheader(f"Resource state at tick {tick}")
cols = st.columns(len(RESOURCES))
for col, (name, info) in zip(cols, snap["resources"].items()):
    with col:
        st.markdown(f"**{name}**")
        used = info["used"]
        predicted = info["predicted"]
        cap = info["capacity"]
        st.progress(min(1.0, (used + predicted) / cap))
        st.write(f"Active: {used}/{cap}")
        st.write(f"Predicted (pre-reserved): {predicted}")
        st.write(f"Queued waiting: {info['queue_len']}")

# ---- Event log up to current tick ----
st.subheader("Event log")
log_lines = []
for s in history[: tick + 1]:
    for t_, line in s["log"]:
        log_lines.append(f"[t={t_}] {line}")

st.text_area("Log", value="\n".join(log_lines[-200:]), height=300)

# ---- Stats that judges like to see ----
st.subheader("Controller effectiveness")
total_queued_events = sum(
    1 for s in history[: tick + 1] for _, line in s["log"] if "QUEUED" in line
)
total_predicted = sum(
    1 for s in history[: tick + 1] for _, line in s["log"] if "pre-reserved" in line and "CONFIRMED" not in line
)
total_confirmed = sum(
    1 for s in history[: tick + 1] for _, line in s["log"] if "CONFIRMED" in line
)
c1, c2, c3 = st.columns(3)
c1.metric("Times an agent had to queue", total_queued_events)
c2.metric("Predictive pre-reservations made", total_predicted)
c3.metric("Predictions later confirmed used", total_confirmed)

if autoplay and tick < len(history) - 1:
    time.sleep(0.4)
    st.session_state.tick = tick + 1
    st.rerun()
