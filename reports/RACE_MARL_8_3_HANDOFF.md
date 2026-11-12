# RACE-MARL Stage 8.3 — Handoff

**Status:** COMPLETE — research decision **PARTIAL**  
**Starting commit:** `0bc70600424b96fd3029ba880a8518cfd5c4f6f1` (or descendant working tree)

## Deliverables

| Report | Path |
|--------|------|
| Event parity | `reports/RACE_MARL_8_3_EVENT_PARITY.md` |
| Teacher parity | `reports/RACE_MARL_8_3_TEACHER_PARITY.md` |
| Action safety | `reports/RACE_MARL_8_3_ACTION_SAFETY.md` |
| Performance gap | `reports/RACE_MARL_8_3_PERFORMANCE_GAP.md` |
| Learning recovery | `reports/RACE_MARL_8_3_LEARNING_RECOVERY.md` |
| Communication causality | `reports/RACE_MARL_8_3_COMMUNICATION_CAUSALITY.md` |
| Research decision | `reports/RACE_MARL_8_3_RESEARCH_DECISION.md` |
| Handoff | this file |

## Code / tests / scripts

- `src/race_casablanca/marl/env.py` — event parity, charge mask, second-choice claims, zero-delay bid flush, gap diagnostics
- `src/race_casablanca/marl/bc.py` — `NativeBridgeTeacher` intent/execute, weighted BC, native DAgger
- `src/race_casablanca/sim/environment.py` — commitment-safe `request_return_depot`
- Scripts: `run_stage83_{teacher_parity,teacher_divergence,native_bridge,performance_gap,gap_metrics,recovery_study,recovery_greedy_and_curriculum,causality}.py`
- Tests: `tests/test_marl_event_parity.py`, `tests/test_marl_action_safety_matrix.py`, `tests/test_marl_stage83_bridge.py`

## Follow-up completeness (post-PARTIAL)

- Request-level divergence traces: `stage83_teacher_divergence_*` (normal/peak/tight, SOC=0.35, delay 0/30)
- Fine gap metrics: `stage83_gap_metrics_*` (claims, idle+pending, missed feasible, held-out imitation)
- Greedy row + curriculum map: recovery summary + `stage83_curriculum_map.json`
- Adversarial action-safety matrix: tests green

## Key numbers (development scenarios)

| Method | Mean OT |
|--------|---------|
| NL selective / full | 0.832 |
| Native bridge execute | ~0.821 |
| Factorized intent teacher | 0.597 |
| BC+DAgger / MAPPO A,C,D | ~0.629 |
| MAPPO F,E | ~0.564 |
| Stage 8.2 learned (historical) | ~0.49 |

## Preserve

Stage 8.2 artifacts remain historical under `stage82_*`. Stage 8.3 writes `stage83_*` only.

## Stop

Stage 8.3 ends here. Do not claim PASS. Next: deliberate pivot to non-learning communication paper **or** a narrow sequential/two-phase factorized parity fix — not Stage 9 locked final for MARL superiority.
