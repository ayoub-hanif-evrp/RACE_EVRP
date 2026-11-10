# RACE-MARL — Training validation

## Implementation

- Parameter-shared actor + centralized critic (MAPPO / CTDE).
- Clipped PPO, GAE, entropy bonus, grad clip.
- Real `torch` autograd updates (`scripts/train_race_marl.py`).
- Casablanca train pool via `race_casablanca.marl.scenarios` (frozen geo inputs; no locked_final tuning).

## Smoke evidence

`tests/test_race_marl_smoke.py` and smoke mode require parameter change + checkpoint I/O. **PASS**.

## Milestone 3 — Casablanca training

| Seed | Final eval OT | Updates | Wall (s) | Params changed |
| --- | ---: | ---: | ---: | --- |
| 0 | 0.041666666666666664 | 40 | 1365.6 | True |
| 1 | 0.41666666666666663 | 40 | 1275.61 | True |

### Held-out / validation diagnostic (evaluate_race_marl.py)

| seed | mean_ot | mean_served | n_scenarios |
| --- | --- | --- | --- |
| 0.000 | 0.111 | 1.333 | 6.000 |
| 1.000 | 0.247 | 5.667 | 6.000 |

Checkpoints under `data/casablanca/online_results/marl_checkpoints/casablanca_F_race_marl_seed*_best.pt`.

Milestone wall clock (pipeline): `n/a` s.

## Milestone status

**PASS** for reproducible Casablanca MAPPO training with real gradients and saved checkpoints.
Learning curves / multi-seed CI remain compact (seeds 0–1); not a full large-N study.
