# RACE-MARL — Training validation

## Implementation

- Parameter-shared actor + centralized critic (MAPPO / CTDE).
- Clipped PPO, GAE, entropy bonus, grad clip.
- Real `torch` autograd updates (`scripts/train_race_marl.py`).

## Smoke evidence

`tests/test_race_marl_smoke.py` and `scripts/train_race_marl.py` require:

1. Neural forward passes with action masks.
2. Trajectory collection.
3. Non-zero loss backward.
4. **Actor parameters change** after updates.
5. Checkpoint save/load path under `data/casablanca/online_results/marl_checkpoints/`.

## Milestone status

**PASS** for toy synthetic smoke training.  
**NOT YET** Casablanca-scale learned superiority (Milestone 3+).
