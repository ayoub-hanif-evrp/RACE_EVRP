# Stage 5.1 — Handoff

## Status: COMPLETE — Decision **B** (no methodological advantage)

| Task | Result |
| --- | --- |
| T1 Projection modes | Fixed + tests |
| T2 Readiness charging | Shared controller; +3 peak vs no-ready |
| T3–T4 Cache + incumbent | Logged; opt rarely wins; timeouts explicit |
| T5 Exact crosscheck claim A | Pass |
| T6 Baseline reconciliation | Documented; 5.1 canonical |
| T7 Train comparison | greedy_07 dominates |
| T8 Binding decision | **B** |

### Artifacts

- `reports/STAGE5_1_*.md`
- `scripts/run_stage5_1_decision.py`
- `data/casablanca/online_results/stage5_1_decision.*`
- `data/casablanca/online_results/stage5_1_exact_crosscheck.json`
- `src/race_casablanca/policies/readiness_charging.py`
- `src/race_casablanca/exact/dp_crosscheck.py`

### STOP

No Stage 5.2. No new algorithm family. No PPO/GNN/MARL. No Casablanca rebuild.

**Next if continuing the project:** Stage 6 locked evaluation around **greedy charge-to-0.7** (+ SF-RH 0.7 reference), with RACE-RH documented as negative control — or Stage 7 manuscript-scope assessment without claiming RACE-RH superiority.
