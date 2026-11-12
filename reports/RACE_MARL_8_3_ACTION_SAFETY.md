# RACE-MARL Stage 8.3 — Action Safety

## Charging contract

`OP_CHARGE` is legal only when all hold:

1. Vehicle is idle (not SERVING / CHARGING / EN_ROUTE / EMERGENCY).
2. Battery below charge-to-70% target.
3. No feasible announced pickup exists (readiness charge, matching `RaceCooperativePolicy._maybe_charge`).

Illegal charge actions are clamped to DEFER at step time.

## Commitment preservation

`OnlineSimulator.request_return_depot`: if the vehicle has pickup plan entries or commitments, append/refresh a depot stop; never replace the pickup route.

## Batched claiming

Losers of a contested simultaneous claim may take a **second-choice** feasible announced task using only local peer bids (`n_second_choice_claims`). Duplicate simultaneous proposals are counted (`n_duplicate_task_proposals`).

## Adversarial tests (Task 3)

`tests/test_marl_event_parity.py` + `tests/test_marl_action_safety_matrix.py`:

| State / case | Check |
|--------------|--------|
| Idle + feasible pickup | Charge masked |
| Serving / en-route with commitments | Depot/charge does not wipe pickups |
| Depot-idle low SOC, no feasible | Charge allowed when legal |
| Simultaneous same-task proposals | Counters safe; claims resolve without crash |
| Full toy episode | Battery ≥ 0 (no hard safety violation) |

All listed tests pass (`pytest tests/test_marl_action_safety_matrix.py tests/test_marl_event_parity.py`).
