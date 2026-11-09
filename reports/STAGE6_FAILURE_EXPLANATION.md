# Stage 6 — Why RACE-RH underperforms (matched-trace diagnosis)

**Artifacts:** `data/casablanca/online_results/stage6_failure_diagnosis.json`, `stage6_failure_diagnosis_requests.csv`  
**Runner:** `scripts/run_stage6_failure_diagnosis.py`  
**No new policy implemented.**

## Aggregate search behaviour (full comparison, n=68 SOC35)

| Counter | RACE-RH mean |
| --- | ---: |
| Optimized plans selected | **≈ 0** |
| Incumbent plans selected | high (tens per episode) |
| Timeouts | ≈ 22 |
| Decision runtime | ≈ 23 s |

## Matched request-level traces (greedy→70% vs RACE-RH, SOC35)

| Scenario | Greedy OT | RACE OT | Greedy-only successes | RACE-only successes | Both OK | Both fail | Optimized chosen |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| release peak seed2 | 0.900 (36/40) | 0.825 (33/40) | 5 | 2 | 31 | 2 | 0 |
| release peak seed5 | 0.800 | 0.800 | 2 | 2 | 30 | 6 | 0 |
| release tight seed3 | 0.700 | 0.667 | 2 | 1 | 19 | 8 | 0 |
| eval peak 1201 | 0.850 | 0.775 | 4 | 1 | 30 | 5 | 0 |
| eval peak 1202 | 0.800 | **0.900** | 1 | 5 | 31 | 3 | 0 |

Request IDs and status pairs for every mismatch are in the CSV.

## Causal reading

1. **Search rarely (almost never) improves the incumbent** — differences come from the incumbent/readiness path, not from accepted optimized plans.
2. **Where greedy wins**, RACE typically leaves requests `EXPIRED`/`MISSED`/`REJECTED` after different charge/assignment timing under the same release stream (fixed sim seed).
3. **Where RACE wins** (e.g. peak 1202), it is still with `n_chose_optimized=0` — i.e. readiness + incumbent insertion luck, not optimizer success.
4. **Not a Stage 5.1 simulator defect** — repaired projection/readiness remain in force; the limitation is algorithmic / objective / compute-budget under online unknown futures.

## Classification

**Algorithmic limitation** under the current online commitment objective and search budget. Dataset scale uncertainty is secondary: the full 68-scenario paired CI for RACE − greedy is entirely negative on SOC35.
