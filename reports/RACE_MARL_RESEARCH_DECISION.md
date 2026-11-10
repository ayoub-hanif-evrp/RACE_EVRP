# RACE-MARL — Research decision

## Stage 8 (historical)

Executed MAPPO smoke + compact A–F ablations, but the learning formulation had structural defects (action competition, missing peer-bid features, flattened GAE, cumulative message penalty, message-triggered decision loops). Those ablation numbers are **not** valid for final claims.

## Stage 8.1 (current)

| Gate | Result |
| --- | --- |
| 1 Correctness | **PASS** |
| 2 Basic learning | **PASS** |
| 3 Casablanca + delay | **PASS** (no pathological 1500-send collapse) |
| 4 Selective RACE novelty | **PARTIAL** — full-comm still leads on compact val |

**Binding decision: PARTIAL — continue to Stage 8.2 multi-seed evaluation after this repaired stack.**

See `reports/RACE_MARL_8_1_HANDOFF.md`.
