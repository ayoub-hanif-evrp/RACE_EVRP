# Stage 6 — Final frozen-policy comparison

**Canonical simulator:** Stage 5.1 (Decision B).  
**Base commit:** `96b1be0` (Stage 5.1 close).  
**Machine results:** `data/casablanca/online_results/stage6_final_comparison.csv` (+ `.json`, `_summary.json`).  
**Runner:** `scripts/run_stage6_final_comparison.py`.

## Design reminder

- Sampling unit = independent scenario.
- Suites: `full_soc` (initial SOC 1.0) and `soc35` (0.35).
- Scenario set: 8 release train + 16 `evaluation_v1/default` (8 baseline + 4 peak + 4 tight in the executed subset as listed in the CSV) → **24 scenario keys**.
- RACE-RH bounded to `soc35` on release + first two peak/tight eval seeds (computational pre-bound, not post-hoc cherry-picking).

## SOC35 mean on-time (all released requests)

| Policy | n scenarios | Mean on-time | Mean runtime (s) | Mean timeouts |
| --- | ---: | ---: | ---: | ---: |
| greedy charge-to-70% | 24 | **0.849** | ~0 | 0 |
| SF-RH charge-to-70% | 24 | 0.852 | ~0 | 0 |
| SF-RH charge-aware | 24 | 0.852 | ~0 | 0 |
| greedy always-full | 24 | 0.812 | ~0 | 0 |
| greedy adaptive | 24 | 0.799 | ~0 | 0 |
| RACE-RH | 12 | 0.792 | **23.1** | **22.6** |

RACE-RH mean served is higher only because its 12-scenario subset is enriched in peak/tight (larger `n_requests`); do not compare absolute served counts across unequal subsets. Use paired differences.

## Paired differences vs greedy charge-to-70% (on-time rate)

| Other policy | n paired | Mean Δ (other − greedy07) | Approx. 95% CI | Wins / ties / greedy wins |
| --- | ---: | ---: | --- | --- |
| RACE-RH | 12 | **−0.014** | [−0.040, +0.012] | 1 / 6 / 5 |
| SF-RH→70% | 24 | +0.003 | [−0.010, +0.016] | 6 / 13 / 5 |
| SF-RH charge-aware | 24 | +0.003 | [−0.010, +0.016] | 6 / 13 / 5 |
| greedy adaptive | 24 | **−0.050** | [−0.081, −0.019] | 3 / 10 / 11 |
| greedy always-full | 24 | **−0.036** | [−0.054, −0.018] | 0 / 12 / 12 |

## Peak SOC35 highlights (release + eval)

Mean on-time among peak scenarios in the CSV:

| Policy | Mean OT (peak soc35) |
| --- | ---: |
| greedy→70% | 0.843 |
| SF-RH→70% / charge-aware | 0.832 |
| RACE-RH | 0.820 |
| greedy always-full | 0.786 |
| greedy adaptive | 0.714 |

Release peak examples remain consistent with Stage 5.1: e.g. seed2 SOC35 greedy 36/40 vs RACE-RH 33/40 (~34 s, 43 timeouts, **0** optimized plans chosen).

## Claim

**No demonstrated methodological advantage for RACE-RH** over greedy charge-to-70% on the Stage 6 paired ensemble. Charge-to-70% remains the strongest simple reference; adaptive / always-full are worse under SOC stress. SF-RH is statistically tied with greedy→70% within CI noise and far cheaper than RACE-RH.
