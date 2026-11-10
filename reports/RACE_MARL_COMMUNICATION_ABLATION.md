# RACE-MARL — Communication ablation status

## Non-learning protocol repairs (Milestone 1)

Completed earlier (async windows, selective expiry, matched random, packet loss, travel-primary ranking).
Compact pilot: `data/casablanca/online_results/race_comm_pilot_v2.csv`.
`full` @ delay>0 skipped in compact pilot due to event-queue blow-up (documented limitation).

## Learned communication ablations (Milestone 4)

Matched MAPPO budget; architecture / reward / action space held fixed except the ablation factor.

### Train diagnostics

| ablation | seed | mean_ot | mean_return | wall_time_s | params_changed |
| --- | --- | --- | --- | --- | --- |
| A_no_comm | 0 | 0.000 | 0.000 | 884.1 | True |
| B_full_comm | 0 | 0.325 | 13.325 | 950.8 | True |
| C_random_matched | 0 | 0.750 | 9.708 | 892.3 | True |
| D_selective | 0 | 0.038 | 1.537 | 924.5 | True |
| E_selective_no_energy | 0 | 0.508 | 9.008 | 993.0 | True |

### Shared diagnostic evaluation

| ablation | seed | mean_ot | mean_served | mean_sends | n_scenarios |
| --- | --- | --- | --- | --- | --- |
| A_no_comm | 0 | 0.389 | 10.167 | 0.000 | 6 |
| B_full_comm | 0 | 0.454 | 12.500 | 18.667 | 6 |
| C_random_matched | 0 | 0.413 | 11.500 | 1.000 | 6 |
| D_selective | 0 | 0.265 | 9.000 | 0.000 | 6 |
| E_selective_no_energy | 0 | 0.426 | 12.000 | 0.000 | 6 |
| F_race_marl | 1 | 0.247 | 5.667 | 10.500 | 6 |

### Honest interpretation (compact n=6 diagnostic)

- **Best learned method here is B (full communication)**, not selective F.
- A (no comm) already beats F on this set; F seed1 is better than F seed0 but still weak on peak_stress.
- D/E often learn near-zero send rates under the current reward (tiny message cost + sparse OT signal).
- Non-learning `full` @ delay>0 remains **skipped** in the compact pilot (event-queue blow-up). Learned transfer under 30 s delay also collapses (OT→0, send spam to max decisions) — async robustness **not** demonstrated.

Raw: `marl_ablations_eval.csv`, `marl_ablations_summary.json`.
