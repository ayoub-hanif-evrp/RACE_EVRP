# Stage 4B — Exact small-instance charge–commitment benchmark

## Model

Module: `src/race_casablanca/exact/charge_commit_enum.py`  
Runner: `scripts/run_stage4b_exact_toys.py` → `data/casablanca/online_results/stage4b_exact_toys.json`

Exact for the **discrete-action** model: deterministic line-graph travel, hard windows, depot-only charges from `{0.50, 0.70, 1.00}`, single vehicle. Enumeration over serve-order permutations with optional charge actions before each serve.

## Instances

| ID | Claim | Result (reference) |
| --- | --- | --- |
| A `early_charge` | Must charge before far pickup (energy/reserve) | best=1; plan charges then serves; greedy/always-full also 1 |
| B `serve_before_charge` | Full charge first misses tight R1 | best=2; always-full=1 |
| C `partial_better` | Charge-to-0.50 fits window; full (and adaptive 0.7) too slow | best=1; greedy=0; always-full=0 |
| D `charge_enables_later` | Mid/early charge enables second request | best=2; always-full=1 (full-first burns R1 window) |

## Baseline match

Always-full **mismatches** the reference on B, C, D. Adaptive/partial-aware greedy mismatches on C (uses 0.7 instead of 0.5). This is a clean discrete-target timing effect, not inverse-slack ranking.

## Tests

`tests/test_stage4b_exact.py`
