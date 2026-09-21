"""
reservation_manager.py
-----------------------
This is the CORE CONTROLLER for the problem statement:
"Runtime Service-Graph Reservation for Multi-Agent Systems"

WHAT IT DOES (in plain English):
- We simulate several "agents" (pretend AI workflows), each of which needs a
  SEQUENCE of resources over time (e.g. Agent-1 needs: GPU -> DB -> API).
- Each resource (GPU, DB, API, IMAGE_MODEL) has limited capacity (slots).
- The ReservationManager below is the "airport control tower":
    1. When an agent needs a resource NOW, it tries to grant a slot.
       If none free -> agent is QUEUED (so nobody starves forever, they just wait
       in line, first-come-first-served).
    2. PREDICTION: while an agent is using its current resource, we peek at what
       it will need NEXT (its next step) and try to PRE-RESERVE that resource
       ahead of time, IF there's spare capacity. This is the "predicts future
       dependencies and reserves ahead of time" part of the problem statement.
       We never let a prediction block a real request (predictions only use
       genuinely spare capacity), which is how we avoid OVER-ALLOCATION.
    3. When an agent finishes using a resource, it's released immediately and
       handed to the next queued agent, if any.

Run this file directly to see a text simulation in your terminal (no
Streamlit needed) - good for quickly checking the logic works before you
wire up the dashboard.
"""

import random
from collections import deque

DEFAULT_DURATION = 3  # ticks a resource is held for when granted from the queue


class ReservationManager:
    def __init__(self, resources: dict):
        """resources: e.g. {"GPU": 2, "API": 3, "DB": 5, "IMAGE_MODEL": 1}"""
        self.capacity = dict(resources)
        # resource -> {agent_id: ticks_remaining}
        self.holders = {r: {} for r in resources}
        # resource -> set(agent_id) that have a PREDICTED (soft) reservation
        self.predicted = {r: set() for r in resources}
        # resource -> deque of agent_ids waiting in line
        self.queue = {r: deque() for r in resources}
        # list of (tick, text) - the event log the dashboard will display
        self.log = []

    def free_slots(self, resource):
        used = len(self.holders[resource]) + len(self.predicted[resource])
        return self.capacity[resource] - used

    def try_reserve(self, tick, agent_id, resource, duration, predicted=False):
        """Try to get `agent_id` a slot on `resource`.
        predicted=True means: this is a look-ahead / speculative reservation
        for a step the agent hasn't reached yet.
        Returns True if granted (or already held/pre-reserved), False if queued/denied.
        """
        # already actually holding it
        if agent_id in self.holders[resource]:
            return True

        # already has a predicted reservation and this call is also predicted -> no-op
        if predicted and agent_id in self.predicted[resource]:
            return True

        # this is a REAL request, and we already predicted it earlier -> confirm it
        if not predicted and agent_id in self.predicted[resource]:
            self.predicted[resource].discard(agent_id)
            self.holders[resource][agent_id] = duration
            self.log.append((tick, f"{agent_id} CONFIRMED pre-reserved {resource}"))
            return True

        if self.free_slots(resource) > 0:
            if predicted:
                self.predicted[resource].add(agent_id)
                self.log.append((tick, f"{agent_id} pre-reserved {resource} (predicted next need)"))
            else:
                self.holders[resource][agent_id] = duration
                self.log.append((tick, f"{agent_id} reserved {resource}"))
            return True

        # no capacity right now
        if not predicted and agent_id not in self.queue[resource]:
            self.queue[resource].append(agent_id)
            self.log.append((tick, f"{agent_id} QUEUED for {resource} (full)"))
        return False

    def tick_update(self, tick):
        """Call once per simulation tick. Decrements active holds, releases
        finished ones, and hands freed slots to the next queued agent.
        Returns list of (agent_id, resource) that FINISHED naturally this tick
        (used by the simulation to advance that agent to its next step)."""
        finished_steps = []
        for resource, holders in self.holders.items():
            done_agents = [a for a, remaining in holders.items() if remaining <= 1]
            for a in holders:
                holders[a] -= 1
            for a in done_agents:
                del holders[a]
                self.log.append((tick, f"{a} released {resource}"))
                finished_steps.append((a, resource))
                if self.queue[resource]:
                    nxt = self.queue[resource].popleft()
                    self.holders[resource][nxt] = DEFAULT_DURATION
                    self.log.append((tick, f"{nxt} granted {resource} from queue"))
        return finished_steps

    def snapshot(self):
        """A picture of current resource usage, for the dashboard to draw."""
        return {
            r: {
                "capacity": self.capacity[r],
                "used": len(self.holders[r]),
                "predicted": len(self.predicted[r]),
                "queue_len": len(self.queue[r]),
            }
            for r in self.capacity
        }


def make_agents(resource_names, num_agents=6, max_ticks=40, seed=42):
    """Creates fake agents, each with a random sequence of resource needs."""
    rng = random.Random(seed)
    agents = []
    for i in range(num_agents):
        seq_len = rng.randint(3, 5)
        seq = [rng.choice(resource_names) for _ in range(seq_len)]
        durations = [rng.randint(2, 4) for _ in seq]
        arrival = rng.randint(0, max_ticks // 3)
        agents.append({
            "id": f"Agent-{i+1}",
            "seq": seq,
            "durations": durations,
            "arrival": arrival,
            "idx": 0,
        })
    return agents


def run_simulation(resources: dict, num_agents=6, ticks=40, seed=42):
    """Runs the whole simulation and returns a HISTORY list: one entry per
    tick, containing a resource snapshot and the log lines from that tick.
    The dashboard just scrubs through this list - no live async needed."""
    mgr = ReservationManager(resources)
    agents = make_agents(list(resources.keys()), num_agents, ticks, seed)

    history = []
    for t in range(ticks):
        tick_start_log_len = len(mgr.log)

        # 1. every active agent tries to reserve its CURRENT step, and
        #    predictively pre-reserve its NEXT step
        for ag in agents:
            if ag["idx"] >= len(ag["seq"]):
                continue
            if t < ag["arrival"]:
                continue
            resource = ag["seq"][ag["idx"]]
            duration = ag["durations"][ag["idx"]]
            if ag["id"] not in mgr.holders[resource] and ag["id"] not in mgr.queue[resource]:
                mgr.try_reserve(t, ag["id"], resource, duration)

            nxt_idx = ag["idx"] + 1
            if nxt_idx < len(ag["seq"]):
                nxt_resource = ag["seq"][nxt_idx]
                nxt_duration = ag["durations"][nxt_idx]
                mgr.try_reserve(t, ag["id"], nxt_resource, nxt_duration, predicted=True)

        # 2. advance time: release finished holds, serve the queue
        finished = mgr.tick_update(t)

        # 3. move finished agents on to their next step
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


if __name__ == "__main__":
    RESOURCES = {"GPU": 2, "API": 3, "DB": 5, "IMAGE_MODEL": 1}
    history, agents = run_simulation(RESOURCES, num_agents=6, ticks=40)
    for snap in history:
        if snap["log"]:
            print(f"--- tick {snap['tick']} ---")
            for _, line in snap["log"]:
                print(" ", line)
    print("\nFinal resource state:")
    print(history[-1]["resources"])
