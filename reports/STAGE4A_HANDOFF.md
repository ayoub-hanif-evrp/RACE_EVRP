# Stage 4A — Handoff

## Status: COMPLETE — acceptance **FAIL**

| Deliverable | Path |
| --- | --- |
| Failure diagnosis | `reports/STAGE4A_FAILURE_DIAGNOSIS.md` |
| Formulation | `reports/STAGE4A_NEW_FORMULATION.md` |
| Experiments | `reports/STAGE4A_EXPERIMENT_RESULTS.md` |
| Literature | `reports/STAGE4A_LITERATURE_POSITIONING.md` |
| Decision | `reports/STAGE4A_RESEARCH_DECISION.md` |
| Policy | `src/race_casablanca/policies/race_postdecision.py` |
| Lookahead | `src/race_casablanca/sim/lookahead.py` |
| Futures model | `src/race_casablanca/demand/synthetic_futures.py` |
| Runner | `scripts/run_stage4a_pilot.py` |
| Results | `data/casablanca/online_results/stage4a_*` |
| Tests | `tests/test_stage4a_postdecision.py` |

## STOP

No neural training. No dataset rebuild. No rehabilitation of inverse-slack RACE.  
Next step only if reformulating around **charging-timing under online EV commitments**, not another shallow anticipatory heuristic.
