# Stage 3B — Handoff

## Status: COMPLETE — acceptance **PARTIAL**

| Deliverable | Path |
| --- | --- |
| Formulation | `reports/STAGE3B_RACE_FORMULATION.md` |
| Validation | `reports/STAGE3B_METHOD_VALIDATION.md` |
| Comparisons | `reports/STAGE3B_BASELINE_COMPARISON.md` |
| Novelty | `reports/STAGE3B_NOVELTY_ASSESSMENT.md` |
| Policy | `src/race_casablanca/policies/race_commitment.py` |
| Runner | `scripts/run_stage3b_race.py` |
| Results | `data/casablanca/online_results/stage3b_*` |
| Tests | `tests/test_stage3b_race.py` |

## Correctness fixes included

1. Partial fleet commits no longer release omitted vehicles.  
2. Message “decision-changing” metric replaced by counterfactual + invocation counters.

## Scientific takeaway

Energy scarcity and charging dominate outcomes. State-dependent flexibility pricing is implemented and ablated; gains are small and inconsistent once charging is equalized. Rolling horizon remains the stronger full-SOC energy baseline.

## STOP

Do not implement PPO, GNNs, transformers, or MARL yet. Do not rebuild Casablanca. Next work should refine the commitment principle or admit reformulation—not scale learning on the current heuristic.
