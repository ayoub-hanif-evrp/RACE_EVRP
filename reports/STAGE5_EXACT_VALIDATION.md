# Stage 5 — Exact / physical validation

## Physics (A1)

`tests/test_stage5_partial_charge_planning.py` — planning honors `target_kwh`; planned vs simulated delivered energy under δ=0.

## Exact enumerator (A2)

`shift_end` enforced on service finish; documented discrete-action subproblem only. Adversarial `test_shift_end_blocks_late_service`.

## Charging DP + RACE-RH

`tests/test_stage5_race_rh.py`:

| Case | Result |
| --- | --- |
| No-charge energy infeasible | DP rejects; with charges accepts |
| Partial vs full under tight TW | Partial feasible; fixed-1.0 infeasible |
| Exact C structural | best=1, always-full=0 |
| Synthetic RACE-RH episode | Serves ≥1; COMPLETED ≡ on-time |
| Locked leg | Immutable under reopt |
| Failed commit | Restores prior plan |
| Ablation fixed-0.7 | Runs |

Gate: these tests must pass before Casablanca claims.
