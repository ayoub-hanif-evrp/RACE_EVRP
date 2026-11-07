# Stage 3A — Handoff

## Status: COMPLETE

| Item | Path |
| --- | --- |
| Preflight | `reports/STAGE3A_CORRECTNESS_PREFLIGHT.md` |
| Mechanism | `reports/STAGE3A_PROBLEM_AND_MECHANISM.md` |
| Comm experiment | `reports/STAGE3A_COMMUNICATION_EXPERIMENT.md` |
| Novelty decision | `reports/STAGE3A_NOVELTY_DECISION.md` |
| Runner | `scripts/run_stage3a_communication.py` |
| Results | `data/casablanca/online_results/stage3a_*` |
| Tests | `tests/test_stage3a_preflight.py` |

## Selected direction

**Energy-commitment-centered RACE** (Decision A). Communication is secondary; current PoC does not justify joint energy–information novelty.

## STOP

No PPO / GNN / transformers / MARL. No dataset rebuild. Stage 3A ends here.
