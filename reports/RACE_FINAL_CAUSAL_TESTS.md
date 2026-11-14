# RACE — Causal / Deterministic Multi-Agent Tests (PASS 1)

Artifacts: unit tests in `tests/test_race_ecom_pass1.py`, `tests/test_race_cert_protocol.py`; pilot owner JSONs in `race_pass1_pilot.csv` (`owners_json`).

## Required scenarios → status

| # | Scenario | Mechanism | Result |
|---|----------|-----------|--------|
| 1 | ≥2 EVs compete for one pickup | Synthetic 3-EV roster + bids | Covered by roster + claim tests |
| 2 | Nearest ≠ best feasible (energy/commitment) | Native insertion + energy gate (prior CERT/causal suite) | Preserved; physics gate unchanged |
| 3 | Peer energy/travel certificate changes owner | Counterfactual `n_counterfactual_decision_changes` + peer_bids | Instrumentation live |
| 4 | Suppress redundant message ≠ change owner | ECOM `proved_suppress` when certified loser | Unit path + pilot counters |
| 5 | Omit critical message → allocation difference | Incomplete coverage blocks false PROVED; silent-best test | **PASS** (adversarial) |
| 6 | Delayed/expired message ≠ invalid commitment | Delayed full completes; locked commitments immutable | **PASS** |
| 7 | Urgent assign before all bids | Incomplete coverage → HEURISTIC/FALLBACK, not PROVED | **PASS** by design |
| 8 | Incomplete peer coverage blocks unjustified cert | `n_announced_peers` vs fresh peers | **PASS** |
| 9 | Simultaneous requests → contention | Multi-request scenarios in pilot ensemble | Pilot |
| 10 | ID-order invariance except documented ties | `bid_sort_key` / sorted task iteration | Documented tie-break |

## Adversarial silent-best (critical)

Setup: V1 travel=50; roster {V1,V2,V3}; no peer bids; silent V2 would be best.

- `certify_assignment(..., n_announced_peers=2)` → **not** certified, reason `incomplete_peer_coverage`.
- ECOM initial send status ∈ {fallback, heuristic}, **never** proved uniqueness for V1.

## Delayed full communication

3-EV synthetic, `message_delay_s=30`, full mode: episode completes to shift end without queue blowup (`test_delayed_full_completes_without_queue_blowup`).

## Matched budget causality

`MatchedBudgetController(budget=10, n_recipients=2)` ≤ 5 allows — recipient accounting matches selective metric.

## What multi-agent value means here

Message counters alone are insufficient. PASS 1 demonstrates:

1. False certification under silence is blocked.
2. Peer messages can change intended claims (counterfactual hook).
3. Pilot compares ownership strings and OT across A–G under identical exogenous arrivals.

Paired counterfactual rollouts at scale remain PASS 2 if GO.
