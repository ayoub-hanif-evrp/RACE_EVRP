# Stage 3B — Baseline comparison

**Source:** `data/casablanca/online_results/stage3b_race_metrics.*`  
**Config:** `stage3b_experiment_config.json`  
**Scenarios:** training only (`baseline_seed1`, `peak_stress_seed2`, `tight_windows_seed3`)  
**RH budget:** 0.25 s per reoptimize  
**35% SOC cases:** hypothetical stress, not observed Casablanca fleet SOC.

## Peak stress (40 requests) — headline table

| Setting | Greedy | RH | RACE | RACE ablation | Restricted none |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full SOC served | 38 | 38 | 38 | 38 | 35 |
| Full SOC energy kWh | 55.56 | **49.32** | 55.56 | 55.56 | 53.37 |
| SOC 35% served | 20 | 21 | **30** | 29 | 18 |
| SOC 35% + δ=0.2 served | 14 | 16 | **28** | 27 | 14 |
| SOC 35% + charge enabled (probe) | **30** | — | **30** | — | — |

## What the ablation isolates

RACE and RACE-ablation both may enable depot charging when idle headroom is low. Differences between them are therefore mainly opportunity-cost pricing and scarcity reassignment:

| Case | RACE − ablation (served) | Energy |
| --- | ---: | --- |
| peak SOC 35% | +1 | 40.65 vs 46.10 (RACE lower) |
| peak SOC 35% δ=0.2 | +1 | 49.82 vs 54.65 (RACE lower) |
| tight SOC 35% | **−2** | similar |
| tight SOC 35% δ=0.2 | +3 | similar |
| all full-SOC suites | 0 | identical to greedy |

## Critical equalization: charging

On peak stress at 35% SOC with **`charge_on_return=True` for greedy**:

- Greedy: 30/40, 39.80 kWh, 8 charges  
- RACE: 30/40, 40.65 kWh, 8 charges, 5 reassignments  

So the large gap vs default greedy (20→30) is **mostly charging recovery**, not flexibility shadow prices. Opportunity cost adds at most a small service edge and sometimes improves energy vs the ablation, but does not dominate a charge-enabled greedy baseline.

## Rolling horizon remains the strong travel/energy baseline

At full battery on peak stress, RH matches greedy/RACE service (38/40) with ~11% less energy (49.32 vs 55.56 kWh) at higher decision runtime (~179 ms mean vs ~24–41 ms).

## Restricted no-communication reference

Same public task registry; no peer-state messages. Service is weakly worse under stress (35/40 full SOC; 18/40 at 35% SOC). This is an information-structure reference, not a claim about communication value (see Stage 3A).

## Runtime

RACE decision means typically 15–115 ms depending on scenario; RH 30–180 ms under the 0.25 s budget.
