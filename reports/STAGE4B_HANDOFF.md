# Stage 4B — Handoff

## Status: COMPLETE — acceptance **PARTIAL**

Hard deadlines + discrete target-SOC depot charging + tiny exact reference + equalized gap diagnostics are in place. A clean **peak-vs-tight charging trade-off** is demonstrated (always-full helps peak SOC35 vs adaptive, but collapses on tight windows; charge-to-0.7 / RH+0.7 dominate). That is enough for reformulation, not for claiming a closed algorithmic PASS: equalized RH+0.7 already captures much of the online gain without a new DP yet.

| Deliverable | Path |
| --- | --- |
| Problem formulation | `reports/STAGE4B_CHARGING_COMMITMENT_PROBLEM.md` |
| Deadline/charge validation | `reports/STAGE4B_DEADLINE_AND_CHARGING_VALIDATION.md` |
| Exact toys A–D | `reports/STAGE4B_EXACT_SMALL_INSTANCE_BENCHMARK.md` |
| Charging gap | `reports/STAGE4B_CHARGING_DECISION_GAP.md` |
| Reformulation | `reports/STAGE4B_RESEARCH_REFORMULATION.md` |
| Exact module | `src/race_casablanca/exact/charge_commit_enum.py` |
| Runners | `scripts/run_stage4b_exact_toys.py`, `scripts/run_stage4b_charging_gap.py` |
| Results | `data/casablanca/online_results/stage4b_*` |
| Tests | `tests/test_stage4b_deadlines_and_charging.py`, `tests/test_stage4b_exact.py` |

Prior FAIL reports (3C, 4A) are unchanged.

## Follow-on (one direction only)

If continuing method work: **discrete target-SOC charging–commitment DP / bounded enumeration** with the same action alphabet — not inverse-slack, not Stage 4A MC revival, not neural nets.

## STOP

No Casablanca rebuild; no PPO/GNN/MARL; no communication revival; no large training; do not rehabilitate Stage 3C/4A heuristics.
