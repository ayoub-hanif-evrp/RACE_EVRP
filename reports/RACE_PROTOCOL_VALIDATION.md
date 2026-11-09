# RACE-COMM — Protocol validation (Phase 3)

## Safety / information boundary

| Check | Result |
| --- | --- |
| Restricted `ActionInterface.get_simulator()` | Raises `PermissionError` |
| Legacy `actions._sim` under restricted actor | Same block (property → `get_simulator`) |
| Peer bids only after delivery / zero-delay flush | `local_bids` updated on `task_bid` deliver |
| Atomic ownership | Unchanged `TaskRegistry` |
| Hard feasibility at claim | Fresh `check_insertion` + `try_assign` |

Tests: `tests/test_race_cooperative.py`, existing Stage 2.1 adversarial suite.

## Deterministic ranking properties

- Feasible bids ranked by marginal travel ↑, then energy flexibility ↓, then slack ↓, then vehicle id.
- `self_should_claim` defers when a fresh peer bid ranks better.
- Two-phase `bid_exchange` → `bid_assign` on request release (policy flag `two_phase_bidding`).

## Behavioral evidence (pilot)

On peak SOC35 `peak_stress_seed2`, selective/full produce **16** counterfactual claim changes and **16** peer defers vs **0** under `none`. Service rises 36/40 → 37/40. Messages: selective **85** vs full **193**.

This is assignment-changing communication, not message-count theater.
