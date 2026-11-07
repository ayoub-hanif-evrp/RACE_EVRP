# Stage 3C — Handoff

## Status: COMPLETE — acceptance **FAIL** (current RACE heuristic)

| Deliverable | Path |
| --- | --- |
| Objective audit | `reports/STAGE3C_OBJECTIVE_AND_INSERTION_AUDIT.md` |
| Fair charging | `reports/STAGE3C_FAIR_CHARGING_BASELINES.md` |
| Ablation | `reports/STAGE3C_MECHANISM_ABLATION.md` |
| Decision | `reports/STAGE3C_RESEARCH_DECISION.md` |
| Runner | `scripts/run_stage3c_race.py` |
| Results | `data/casablanca/online_results/stage3c_*` |
| Tests | `tests/test_stage3c_objective.py` |

## Code changes retained

- Marginal insertion metrics + `evaluate_insertion`
- Position-aware RACE / greedy commits (`force_position`)
- Shared `ChargingController` (no global config mutation)
- Independent pricing × reassignment flags

## STOP

No PPO / GNN / transformers / MARL. No Casablanca rebuild. No communication expansion.

Next work, if any, must **reformulate** the commitment-value principle—not deepen inverse-slack RACE or imitate it with neural nets.
