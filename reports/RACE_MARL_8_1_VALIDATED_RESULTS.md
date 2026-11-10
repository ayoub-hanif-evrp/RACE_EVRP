# RACE-MARL Stage 8.1 — Validated results

Artifacts:
- `data/casablanca/online_results/stage81_summary.json` (BC recovery pilot)
- `data/casablanca/online_results/stage81_fair_matrix.csv`
- `data/casablanca/online_results/stage81_fair_matrix_summary.csv`

Matched scenarios (n=6): validation + development diagnostics (not locked_final).

## Gate 2 — Toy recovery

| Metric | Value |
| --- | ---: |
| BC loss first → last | 1.061 → 0.003 |
| MAPPO fine-tune OT | 1.000 |

## Fair matrix @ delay 0 s (mean OT)

| Method | Mean OT | Mean served | Mean msgs |
| --- | ---: | ---: | ---: |
| nl_full | 0.832 | 26.2 | 322 |
| nl_selective | 0.832 | 26.2 | 65 |
| nl_random_matched | 0.824 | 25.8 | 78 |
| nl_none | 0.821 | 25.7 | 0 |
| greedy_charge70 | 0.819 | 25.8 | 0 |
| mappo_B_full_comm | 0.554 | 15.7 | 19 |
| mappo_D_selective | 0.554 | 15.7 | 21 |
| mappo_E_selective_no_energy | 0.554 | 15.7 | 22 |
| mappo_C_random_matched | 0.510 | 14.3 | 7 |
| mappo_A_no_comm | 0.493 | 13.8 | 0 |
| mappo_F_race_marl | 0.458 | 12.7 | 20 |

## Fair matrix @ delay 30 s

| Method | Mean OT | Mean msgs | Notes |
| --- | ---: | ---: | --- |
| greedy_charge70 | 0.819 | 0 | privileged centralized |
| nl_none / selective / random_matched | ~0.801 | 0–69 | |
| mappo_B | 0.554 | 19 | no collapse |
| mappo_A | 0.493 | 0 | |
| mappo_F | 0.458 | 20 | **was 0 OT / ~1500 sends in Stage 8** |
| nl_full | — | — | skipped (event-queue blow-up) |

## Part 9 essential questions (this matrix)

| Question | Answer on this set |
| --- | --- |
| A. Peer info help same learned task policy? | **Yes** — B 0.554 > A 0.493 |
| B. Selective save msgs vs full at similar service? | **Unclear** — D≈B OT, msgs similar (~21 vs 19) |
| C. Selective beat random matched? | **Yes** — D 0.554 > C 0.510 |
| D. Energy bid features help? | **No measured gain** — D≈E |
| E. Useful under delay? | **Stable** — F delay OT=0.458, ~20 sends |
| F. Transfer 3→5 EVs? | **Yes / helpful** — F seed1_best mean OT 0.531 @3 EV → **0.900 @5 EV** (`stage81_F_nv3/5.csv`) |

## Multi-seed checkpoints

Trained Stage 8.1 MAPPO A–F for seeds 0 and 1 (`marl_checkpoints/stage81_*_seed{0,1}*_best.pt`).

## Interpretation

Corrected MARL **recovers service and delay robustness**, and shows peer-info and selective>random signals. It remains **well below** the non-learning cooperative teacher (~0.83). Distinctive energy-aware selective novelty is **not** established.
