# Runtime Service-Graph Reservation - Hackathon Starter

This is a **working, runnable MVP** for the PS: predicting and reserving
resources for concurrent agent workflows, without over-allocation or starvation.

## Files
- `reservation_manager.py` - the controller "brain": reservation manager,
  predictive pre-reservation, queueing, and the simulation engine.
- `dashboard.py` - Streamlit UI: live-feeling resource bars, event log, and
  effectiveness stats, scrubbed via a tick slider.

## How to run it (do this first, right now)
```bash
pip install streamlit
streamlit run dashboard.py
```
It'll open in your browser. Drag the "Tick" slider (or check "Autoplay") to
watch agents reserve, get queued, get pre-reserved, and release resources.

## How this maps to the plan
- **Step 3 (reservation manager)** = `ReservationManager` class in
  `reservation_manager.py`. Grant / queue / release logic lives there.
- **Step 4 (prediction layer)** = the `predicted=True` calls to
  `try_reserve()` - it looks at each agent's NEXT step and soft-reserves it
  ahead of time, only using genuinely spare capacity.
- **Step 5 (dashboard)** = `dashboard.py`.
- **Step 6 (integrate)** = these two files already work together - just run
  the command above.

## What to say in your 90-second pitch
1. **Problem**: concurrent agent workflows compete for shared resources
   (models, APIs, DBs). Naive systems either over-allocate (waste) or let
   some agents starve (unfair/slow).
2. **Our approach**: each agent's workflow is a sequence of resource needs.
   Our controller doesn't just react - it looks one step ahead in that
   sequence and pre-reserves the next resource *if and only if* there's spare
   capacity, so the hand-off between steps is instant with zero waste.
3. **Fairness**: when a resource is full, agents queue FIFO - guaranteed no
   starvation.
4. **Demo**: show the dashboard - point at the "Predicted" vs "Active" counts
   and the "Queued waiting" number dropping to 0 over time.

## If you have extra time before 8 AM (optional, in priority order)
1. Swap the "predicted next resource" logic for a slightly smarter version:
   instead of just "always look 1 step ahead", track how often each
   resource->resource transition happens across all agents and prioritize
   pre-reserving the *most likely* next resource. This lets you legitimately
   say "we use historical pattern frequency to predict demand."
2. Add a second chart: total wasted pre-reservations (predicted but never
   confirmed) vs. capacity - this directly demonstrates you AVOID
   over-allocation, which is literally in the problem statement's wording.
3. Let a user upload/define their own agents and resources from the sidebar
   instead of only the built-in random generator.

Do not attempt all three - pick at most one, only if the core demo is solid
and tested by ~2 AM.
