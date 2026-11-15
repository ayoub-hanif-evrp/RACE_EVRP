# Energy / Deadline Wait Validity

## Authority

The assign window is **centrally scheduled** by `OnlineSimulator._maybe_decide` after `bid_exchange` (one wait per request). It is **not** a fully decentralized per-EV wait vote. Claims remain local after the window opens.

## What wait uses (repaired)

`RaceCooperativePolicy.assignment_wait_for_request()` now:

1. Probes **each EV’s own** `sim.check_insertion(vid, request_id)` for feasibility and marginal travel (no peer bid tables).
2. Passes real `local_feasible` and `local_travel_s` into `deadline_energy_assignment_wait_s`.
3. Counts fresh peer coverage from **one viewer’s** `local_bids[viewer]` only (not a merged global table).

Counter `n_wait_used_local_travel` increments when a feasible travel estimate exists.

## What wait is not

- Not a claim that decentralized agents jointly optimize wait.
- Not using peer travel rankings to set wait length.
- Energy safety of the eventual claim still relies on the conservative insertion gate at commit time.

## Factorial evidence (pilot)

Under delay, arms that share the deadline-energy wait schedule (`H_CURRENT`, `H_NO_PEER`, `NONE_MATCHED_WAIT`) share identical mean assign waits — messaging does not change wait when peers are ignored.
