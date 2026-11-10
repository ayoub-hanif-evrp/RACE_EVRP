# RACE-MARL Stage 8.1 — Handoff

## Decision: **PARTIAL**

| Gate | Result |
| --- | --- |
| 1 Correctness | **PASS** |
| 2 Basic learning | **PASS** |
| 3 Casablanca val + nonzero delay without pathology | **PASS** |
| 4 Distinctive selective / energy-aware novelty | **PARTIAL** — peer helps; selective>random; still << non-learning teacher; energy features flat |

## Completed deliverables

- Factorized MAPPO stack + BC warm-start
- Fair matched matrix: non-learning none/full/selective/random_matched, greedy charge-70%, MAPPO A–F
- Multi-seed checkpoints A–F seeds 0/1
- Delay-30 stress without send-loop collapse
- 3→5 EV transfer eval for F
- Tests `tests/test_marl_*.py` + reports `RACE_MARL_8_1_*.md`
- Scripts: `run_stage81_repair.py`, `run_stage81_fair_matrix.py`

## Key numbers (matched n=6, delay 0)

- Best non-learning: selective/full OT **0.832**
- Best learned: B/D/E OT **0.554**
- F RACE-MARL OT **0.458** (fair matrix seed0 prefer) / **0.531** (seed1_best alone)
- F @30s: OT **0.458**, ~20 sends (Stage 8 had 0 / ~1500)

## Next (Stage 8.2)

Close the teacher gap with more training budget / better BC from `RaceCooperativePolicy`; multi-seed CIs; only then Stage 9 locked tests if selective energy-aware communication earns a clear edge.
