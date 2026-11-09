# Stage 6 — Final frozen-policy comparison (complete)

**Canonical simulator:** Stage 5.1 (Decision B).  
**Machine results:** `data/casablanca/online_results/stage6_final_comparison.csv` (+ `.json`, `_summary.json`).  
**Runner:** `scripts/run_stage6_final_comparison.py` (checkpoint/resume).  
**Fairness:** all 6 frozen policies × `{full_soc, soc35}` × **68** scenarios (8 release train + **60** `evaluation_v1/default`).  
**Locked final set:** not used.

Total runs: **816**.

## SOC35 policy means (n=68 scenarios)

| Policy | Mean OT | Mean dist (m) | Drive energy (kWh) | Charge energy (kWh) | Mean expired | Mean rejected | Runtime (s) | Timeouts | Opt. chosen |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| greedy→70% | **0.839** | 173425 | 34.69 | 76.69 | 1.35 | 3.57 | ~0 | 0 | n/a |
| SF-RH→70% | 0.844 | 175636 | 35.13 | 77.13 | 1.32 | 3.51 | ~0 | 0 | — |
| SF-RH charge-aware | 0.843 | 174430 | 34.89 | 77.49 | 1.32 | 3.54 | ~0 | 0 | — |
| RACE-RH | 0.829 | 171944 | 34.39 | 83.04 | 1.37 | 3.94 | **22.9** | **21.6** | **0.0** |
| greedy always-full | 0.795 | 159487 | 31.90 | 109.90 | 1.31 | 5.15 | ~0 | 0 | — |
| greedy adaptive | 0.772 | 157704 | 31.54 | 86.26 | 1.29 | 6.10 | ~0 | 0 | — |

Reserve violations and battery exhaustion means are **0** for all policies on this suite. Source: `stage6_final_comparison_summary.json` → `slices.all_soc35`.

## Paired Δ on-time vs greedy→70% (SOC35, n=68)

| Other | Mean Δ | Approx. 95% CI | Wins / ties / greedy wins |
| --- | ---: | --- | --- |
| RACE-RH | **−0.010** | **[−0.019, −0.002]** | 7 / 41 / 20 |
| SF-RH→70% | +0.005 | [−0.006, +0.015] | 17 / 36 / 15 |
| SF-RH charge-aware | +0.004 | [−0.007, +0.014] | 17 / 36 / 15 |
| greedy adaptive | −0.067 | [−0.085, −0.048] | 5 / 23 / 40 |
| greedy always-full | −0.044 | [−0.056, −0.032] | 1 / 29 / 38 |

Eval-only SOC35 (n=60) shows the same ranking: RACE-RH mean Δ ≈ −0.008 (CI upper bound ≈ 0).

## Full-SOC paired (n=68)

RACE-RH mean Δ ≈ **−0.008** (CI entirely negative). Greedy→70% remains competitive; always-full is slightly worse.

## Claim

On the complete Stage 6 paired ensemble, **RACE-RH is statistically not better than greedy charge-to-70%** and is slightly worse on mean on-time under SOC35, at ~23 s mean decision cost with ~22 timeouts and **essentially zero optimized-plan selections**.

Paper-scope decision **B** stands.
