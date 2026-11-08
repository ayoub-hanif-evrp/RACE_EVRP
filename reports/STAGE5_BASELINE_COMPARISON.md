# Stage 5 — Baseline comparison (train)

Artifact: `data/casablanca/online_results/stage5_race_rh.csv`  
Budget default 0.5s for RH-family. Hard deadlines + discrete targets equalized.

## Peak stress × SOC 0.35 (primary stress)

| Policy | on_time_all | served | kWh delivered |
| --- | ---: | ---: | ---: |
| greedy_adaptive_full | 0.675 | 27/40 | 101.0 |
| greedy_always_full | 0.825 | 33/40 | 120.7 |
| **greedy_charge_07** | **0.925** | **37/40** | 87.6 |
| sf_rh_adaptive | 0.700 | 28/40 | 100.6 |
| sf_rh_07 | 0.825 | 33/40 | 91.4 |
| sf_rh_charge_aware | 0.500 | 20/40 | 0.0 |
| race_rh | 0.825 | 33/40 | 87.5 |

RACE-RH matches always-full / sf_rh_07 but **does not beat** greedy charge-to-0.7. Post-hoc `sf_rh_charge_aware` under-charged in this run (deliv=0); treat greedy_07 / sf_rh_07 as the strong equalized references.

## Tight windows × SOC 0.35

| Policy | on_time_all | served |
| --- | ---: | ---: |
| greedy_adaptive_full | 0.700 | 21/30 |
| greedy_always_full | 0.500 | 15/30 |
| greedy_charge_07 | 0.600 | 18/30 |
| sf_rh_07 | **0.733** | **22/30** |
| race_rh | 0.633 | 19/30 |

Always-full still destroys tight windows. RACE-RH loses to sf_rh_07.

## Peak × SOC35 × δ=0.2

greedy_07 **0.875** > race_rh **0.800** > always-full **0.800** > adaptive **0.625**.

## Budget sweep (peak SOC35)

race_rh ≈ 0.775–0.825 across 0.25/0.5/1.0s with many timeouts; wall-clock decision runtime often exceeds the nominal budget because DP is invoked per candidate. No clear service gain from larger budget in this sweep.

## Verdict on competitiveness

No demonstrated advantage of RACE-RH over the best equalized discrete-target baselines on these train scenarios.
