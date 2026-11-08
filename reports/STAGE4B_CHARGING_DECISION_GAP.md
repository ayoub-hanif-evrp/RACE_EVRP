# Stage 4B — Charging decision gap (equalized diagnostic)

Runner: `scripts/run_stage4b_charging_gap.py`  
Artifacts: `data/casablanca/online_results/stage4b_charging_gap.{csv,json}`  
Train only: `baseline_seed1`, `peak_stress_seed2`, `tight_windows_seed3` × `{full_soc, soc35}` (+ `peak` × `soc35_delta02`).

## Equalized action set

All arms use hard-deadline simulator + discrete target-SOC depot charges. No charging disabled for competitive arms. No test/val tuning.

| Policy | Charge rule |
| --- | --- |
| greedy_adaptive_full | adaptive headroom → target 1.0 |
| greedy_always_full | always charge → 1.0 |
| greedy_charge_07 | charge-to-target 0.70 |
| service_first_rh_adaptive | RH + adaptive → 1.0 |
| service_first_rh_07 | RH + charge-to-target 0.70 |

## Headline on-time/all

### Peak stress × SOC 0.35

| Policy | on_time_all | served | kWh delivered | charge_s |
| --- | ---: | ---: | ---: | ---: |
| greedy_adaptive_full | 0.675 | 27/40 | 101.0 | 16533 |
| greedy_always_full | 0.825 | 33/40 | 120.7 | 19752 |
| greedy_charge_07 | 0.850 | 34/40 | 90.6 | 14820 |
| service_first_rh_adaptive | 0.750 | 30/40 | 101.8 | 16665 |
| service_first_rh_07 | **0.875** | **35/40** | 95.5 | 15630 |

### Tight windows × SOC 0.35

| Policy | on_time_all | served | missed |
| --- | ---: | ---: | ---: |
| greedy_adaptive_full | 0.700 | 21/30 | 0 |
| greedy_always_full | **0.500** | 15/30 | 3 |
| greedy_charge_07 | 0.700 | 21/30 | 0 |
| service_first_rh_adaptive | 0.600 | 18/30 | 0 |
| service_first_rh_07 | **0.733** | **22/30** | 0 |

### Tight windows × full SOC

Always-full **hurts** (0.733 vs adaptive/0.7 at 0.867) via overlong depot dwell (`n_missed=3`).

### Peak × SOC35 × δ=0.2

Same ranking: charge-to-0.7 ≥ always-full ≫ adaptive (0.850 / 0.800 / 0.625).

## Interpretation

1. **Peak vs tight trade-off:** always-full helps energy-starved peak relative to adaptive-full, but burns tight windows.
2. **Partial target 0.70** dominates always-full on tight and matches/beats it on peak SOC35.
3. **Service-first RH + 0.7** is best equalized online arm on peak/tight SOC35; residual gap vs weaker charge rules is **timing/target choice**, not inverse-slack.
4. Hard-deadline misses appear under always-full on tight and under adaptive on peak SOC35 (`deadline_on_arrival` / expired).

Charging is **not** disabled; differences are among equalized discrete targets.
