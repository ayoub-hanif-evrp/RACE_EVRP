# MARL Training Data Protocol (Casablanca)

## Problem

The on-disk release has only **8 train scenarios**. That is enough for diagnostics, **not** for serious multi-agent RL training.

## Solution (implemented)

Keep the **same scientific Casablanca geography**, and train on **on-the-fly synthetic episodes** from the frozen demand generator.

| Split | Source | Size intent |
|---|---|---|
| **Train** | Procedural generator, seeds `10_000_000`–`19_999_999` | ≥2000 episodes (recommended 5000) |
| **Validation** | `evaluation_v1/default` | 60 fixed scenarios |
| **Final test** | `evaluation_v1/locked_final` | 30 fixed; **never train/tune** |

Config: [`configs/marl_training_protocol.json`](../configs/marl_training_protocol.json)  
Code: [`src/race_casablanca/marl/episode_sampler.py`](../src/race_casablanca/marl/episode_sampler.py), [`seed_banks.py`](../src/race_casablanca/marl/seed_banks.py)

## What is real vs synthetic

- **Frozen real/derived:** OSM drive graph, pickup candidates, HCP zone weights, Waze-style TTI, depot node, fleet YAML, regime templates.
- **Synthetic each episode:** request locations (sampled from candidates), release times, time windows, weights, service durations.
- **Claim:** geographically grounded **simulation** training stream — **not** observed courier orders.

## Contamination rules

Training seeds are **disjoint** from:

- release train/val/test (`1–8`, `101–102`, `201–203`)
- `evaluation_v1/default` (`1101–1120`, `1201–1220`, `1301–1320`)
- `locked_final` / registered locked banks (`2101–2130`, `2201–2230`, `2301–2330`)

Violations raise errors in `assert_train_seed_allowed`.

## Curriculum

Default `round_robin`: baseline → peak_stress → tight_windows → …  
This exposes the policy to easy and hard time-window regimes.

## How to train

```bash
# Serious Casablanca MARL training (procedural episodes)
python scripts/train_race_marl.py --mode casablanca --episode-source procedural \
  --curriculum round_robin --iters 200 --steps 256 --seed 0 \
  --bc-cooperative --out data/casablanca/online_results/marl_checkpoints/casablanca_procedural.pt
```

Legacy 8-file pool (not recommended for capacity):

```bash
python scripts/train_race_marl.py --mode casablanca --episode-source fixed_pool ...
```

## Scientific honesty

- This makes the dataset **large enough for training**.
- It does **not** create a real Casablanca courier dataset.
- Final claims must still be validated on **locked_final** (or a new holdout), with service / time-window metrics first.
