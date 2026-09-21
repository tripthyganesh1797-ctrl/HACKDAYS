"""
reservation_manager.py
-----------------------
CORE CONTROLLER with Probabilistic Transition Predictions
"Runtime Service-Graph Reservation for Multi-Agent Systems"

WHAT IT DOES:
1. Manages shared capacity across GPU, API, DB, and IMAGE_MODEL.
2. Serves active requests with FIFO queuing (guarantees NO STARVATION).
3. Uses a Markov Transition Matrix to calculate the probability of the NEXT
   tool dependency and issues soft pre-reservations ONLY when spare capacity exists
   (prevents OVER-ALLOCATION).
4. REAL DEMAND ALWAYS BEATS A PREDICTION: if a resource looks full only because
   of soft (predicted) reservations, and a real request arrives, the weakest
   prediction is evicted to make room. A guess must never block real, present
   work - otherwise predictions could accidentally cause the exact starvation
   the controller is supposed to prevent.
"""

import random
from collections import deque

DEFAULT_DURATION = 3  # Ticks a resource is held when granted

# Transition probability matrix: P(Next_Tool | Current_Tool)
SERVICE_TRANSITIONS = {
    "GPU": {"DB": 0.6, "API": 0.3, "IMAGE_MODEL": 0.1},
    "API": {"DB": 0.5, "GPU": 0.3, "IMAGE_MODEL": 0.2},
    "DB": {"API": 0.5, "IMAGE_MODEL": 0.3, "GPU": 0.2},
    "IMAGE_MODEL": {"DB": 0.7, "API": 0.3, "GPU": 0.0},
}


class ReservationManager:
    def __init__(self, resources: dict):
        """resources: e.g. {"GPU": 2, "API": 3, "DB": 5, "IMAGE_MODEL": 1}"""
        self.capacity = dict(resources)
        # resource -> {agent_id: ticks_remaining}
        self.holders = {r: {} for r in resources}
        # resource -> {agent_id: probability} for PREDICTED (soft) reservations
        self.predicted = {r: {} for r in resources}
        # resource -> deque of agent_ids waiting in line
        self.queue = {r: deque() for r in resources}
        # list of (tick, text) - event log for the dashboard
        self.log = []

    def free_slots(self, resource):
        """Calculates free capacity minus active holds and soft pre-reservations."""
        used = len(self.holders[resource]) + len(self.predicted[resource])
        return self.capacity[resource] - used

    def _evict_weakest_prediction(self, tick, resource, evicted_by):
        """Removes the lowest-confidence soft prediction on `resource` to make
        room for a REAL request. Returns True if an eviction happened."""
        preds = self.predicted[resource]
        if not preds:
            return False
        # Evict the prediction the controller trusted least (lowest probability)
        weakest_agent = min(preds, key=lambda a: preds[a])
        weakest_prob = preds.pop(weakest_agent)
        self.log.append((
            tick,
            f"{evicted_by} (real demand) preempted {weakest_agent}'s "
            f"speculative hold on {resource} (was P={weakest_prob:.0%})"
        ))
        return True

    def try_reserve(self, tick, agent_id, resource, duration, predicted=False, probability=1.0):
        """Tries to reserve a slot.
        `predicted=True` creates a soft lock using spare capacity only, and can
        itself be evicted later if real demand needs the room.
        """
        # Already holding the actual slot
        if agent_id in self.holders[resource]:
            return True

        # Already soft-reserved
        if predicted and agent_id in self.predicted[resource]:
            return True

        # REAL request confirming a prior prediction
        if not predicted and agent_id in self.predicted[resource]:
            del self.predicted[resource][agent_id]
            self.holders[resource][agent_id] = duration
            self.log.append((tick, f"{agent_id} CONFIRMED pre-reserved {resource}"))
            return True

        # Has free capacity -> grant slot or soft-reserve
        if self.free_slots(resource) > 0:
            if predicted:
                self.predicted[resource][agent_id] = probability
                self.log.append((tick, f"{agent_id} pre-reserved {resource} (Predicted P={probability:.0%})"))
            else:
                self.holders[resource][agent_id] = duration
                self.log.append((tick, f"{agent_id} reserved {resource}"))
            return True

        # No free capacity. If this is REAL demand, a mere guess should never
        # block it - try evicting the weakest prediction first.
        if not predicted:
            if self._evict_weakest_prediction(tick, resource, evicted_by=agent_id):
                self.holders[resource][agent_id] = duration
                self.log.append((tick, f"{agent_id} reserved {resource}"))
                return True
            if agent_id not in self.queue[resource]:
                self.queue[resource].append(agent_id)
                self.log.append((tick, f"{agent_id} QUEUED for {resource} (Capacity full)"))
        return False

    def tick_update(self, tick):
        """Decrements timers, releases completed holds, and advances FIFO queue."""
        finished_steps = []
        for resource, holders in self.holders.items():
            done_agents = [a for a, remaining in holders.items() if remaining <= 1]

            for a in list(holders.keys()):
                holders[a] -= 1

            for a in done_agents:
                del holders[a]
                self.log.append((tick, f"{a} released {resource}"))
                finished_steps.append((a, resource))

                # Instantly serve next agent in queue
                if self.queue[resource]:
                    nxt = self.queue[resource].popleft()
                    self.holders[resource][nxt] = DEFAULT_DURATION
                    self.log.append((tick, f"{nxt} granted {resource} from queue"))

        return finished_steps

    def snapshot(self):
        """Returns a snapshot of current system utilization."""
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
    """Generates synthetic agent workflows with probabilistic dependencies."""
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
    """Runs the full simulation ticks and builds state history."""
    mgr = ReservationManager(resources)
    agents = make_agents(list(resources.keys()), num_agents, ticks, seed)

    history = []
    for t in range(ticks):
        tick_start_log_len = len(mgr.log)

        # 1. Process active agents & predict downstream needs
        for ag in agents:
            if ag["idx"] >= len(ag["seq"]) or t < ag["arrival"]:
                continue

            curr_resource = ag["seq"][ag["idx"]]
            curr_duration = ag["durations"][ag["idx"]]

            # Request current step (REAL demand - can preempt weak predictions)
            if ag["id"] not in mgr.holders[curr_resource] and ag["id"] not in mgr.queue[curr_resource]:
                mgr.try_reserve(t, ag["id"], curr_resource, curr_duration)

            # Look ahead and pre-reserve using transition matrix probability
            nxt_idx = ag["idx"] + 1
            if nxt_idx < len(ag["seq"]):
                nxt_resource = ag["seq"][nxt_idx]
                nxt_duration = ag["durations"][nxt_idx]

                # Calculate probability from matrix
                prob = SERVICE_TRANSITIONS.get(curr_resource, {}).get(nxt_resource, 0.4)
                if prob >= 0.3:  # Confidence threshold filter
                    mgr.try_reserve(t, ag["id"], nxt_resource, nxt_duration, predicted=True, probability=prob)

        # 2. Advance timers & process queue
        finished = mgr.tick_update(t)

        # 3. Advance completed agents to their next step
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
    print("Simulation completed successfully. Total ticks:", len(history))