# Stage 2.1 — Baseline comparison (one factor at a time)

Executable: `scripts/run_stage2_1_baselines.py`  
Artifacts: `data/casablanca/online_results/stage2_1_baseline_metrics.{csv,json}`

Hard finish-by windows; on-time = service end ≤ `tw_end`.

## Synthetic charging

`synthetic_charge_on`: 1/1 served, **1 charge**, reserve_viol=0.

## Factor: initial SOC (δ=0, full info, charge off) — `baseline_seed1`

| Level | Served | On-time | E (kWh) |
| --- | ---: | ---: | ---: |
| SOC 1.0 | 10/12 | 10 | 24.95 |
| SOC 0.35 | 9/12 | 9 | 21.34 |

## Factor: energy δ (SOC=0.35 fixed)

| δ | Served | E (kWh) | Reserve viol. |
| ---: | ---: | ---: | ---: |
| 0.0 | 9/12 | 21.34 | 0 |
| 0.2 | 8/12 | 21.26 | 0 |

## Factor: information (SOC=1, δ=0)

| Policy | Served | E (kWh) | Msgs |
| --- | ---: | ---: | ---: |
| Full greedy | 10/12 | 24.95 | 0 |
| Restricted | 10/12 | 30.59 | 138 |

Serve rate tied; restricted burns more energy (coordination inefficiency without serve loss on this mild instance).

## Factor: communication delay (restricted only)

| Delay | Served | E (kWh) | Msgs |
| ---: | ---: | ---: | ---: |
| 0 s | 10/12 | 30.59 | 138 |
| 300 s | 10/12 | 29.25 | 132 |

No serve-rate change on baseline.

## Factor: charging (SOC=0.35, δ=0)

| Charge | Served | Charges | E (kWh) |
| --- | ---: | ---: | ---: |
| Off | 9/12 | 0 | 21.34 |
| On | **10/12** | 8 | 25.19 |

Charging is operationally relevant under low SOC.

## Rolling horizon vs greedy (matched full info)

| Policy | Served | E (kWh) |
| --- | ---: | ---: |
| Greedy | 10/12 | 24.95 |
| RH LNS (atomic commit) | 10/12 | 22.76 |

## Peak stress (`peak_stress_seed2`)

| Config | Served | Reserve viol. |
| --- | ---: | ---: |
| SOC1 δ0 full | 38/40 | 0 |
| SOC0.35 δ0 | 20/40 | 0 |
| SOC0.35 δ0.2 | 20/40 | 0 |
| SOC1 δ0.2 | 38/40 | 0 |
| Restricted (SOC1) | **35/40** | 0 |
| SOC0.35 adversarial +δ | 14/40 | **0** |

## Answers (corrected)

1. **Energy active?** Yes under low SOC; δ further tightens baseline service.
2. **Restricted info loss?** Yes on peak stress (−3 served); not on mild baseline serve rate.
3. **Messages change decisions?** Delay alone did not change baseline serve rate; restricted mode changes stress outcomes vs full info.
4. **Charging relevant?** Yes — restores one baseline pickup at SOC 0.35.
5. **Conservative reserve under bound?** Yes — zero violations in OAT and adversarial runs after Stage 2.1 gates.

## Negative / tempered findings

- Mild baseline still too easy for communication to move serve rate.
- RH does not beat greedy on serve count here.
- Do not attribute Stage-2’s old 31→12 collapse to a single factor; corrected OAT separates SOC vs δ.
