# Stage 2 — Baseline results

Executable: `scripts/finish_stage2_baselines.py` (also `scripts/run_online_baselines.py`).  
Artifacts: `data/casablanca/online_results/stage2_baseline_metrics.{csv,json}` (13 executed rows).  
Tests: 20 related unit tests passing (online + travel-time). Stage-1 light verify: PASS.

## Synthetic line network (exact)

| Experiment | Served | On-time | Dist (km) | Energy (kWh) | Returns | Msgs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| synthetic_greedy | 2/2 | 2 | 8.00 | 1.60 | 1 | 0 |
| synthetic_rh | 2/2 | 2 | 8.00 | 1.60 | 1 | 0 |
| synthetic_limited (2 veh) | 2/2 | 2 | 10.00 | 2.00 | 2 | 10 |

## Casablanca `train/baseline_seed1`

| Experiment | Mode | Served | On-time | Dist (km) | E (kWh) | Returns | Charges | Msgs | Reserve viol. | Energy-bind events |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ref_greedy | full | 10/12 | 10 | 152.94 | 30.59 | 10 | 0 | 0 | 0 | 0 |
| ref_rh | full | 10/12 | 10 | **148.67** | 29.73 | 9 | 0 | 0 | 0 | 0 |
| ref_limited | restricted | 10/12 | 10 | 152.94 | 30.59 | 10 | 0 | 138 | 0 | 0 |
| low_soc_greedy (SOC=0.35) | full | **9/12** | 9 | 111.67 | 22.33 | 8 | 0 | 0 | 0 | 0 |
| energy_uncert_greedy (SOC=0.40, δ=0.25) | full | **9/12** | 9 | 119.45 | 23.79 | 8 | 0 | 0 | 0 | 0 |
| fleet1_greedy | full | 10/12 | 9 | 147.04 | 29.41 | 1 | 0 | 0 | 0 | 0 |
| delay_limited (delay=300s, SOC=0.40, δ=0.15) | restricted | 10/12 | 10 | 129.74 | 25.83 | 9 | 0 | 120 | 0 | 0 |

RH slightly reduced distance vs greedy at equal serve rate. Limited-info matched serve rate on this mild instance.

## Casablanca `train/peak_stress_seed2`

| Experiment | Mode | Served | On-time | Dist (km) | E (kWh) | Msgs | Reserve viol. | Energy-bind |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| stress_greedy | full | 31/40 | 28 | 278.49 | 55.70 | 0 | 0 | 0 |
| stress_limited | restricted | 31/40 | 28 | 278.49 | 55.70 | 180 | 0 | 0 |
| stress_low_soc (SOC=0.35, δ=0.2) | full | **12/40** | 7 | 147.90 | 29.15 | 0 | **5** | **2** |

## Answers to Stage-2 research questions

1. **Energy uncertainty / SOC change dispatch?** **Yes.** Default full-SOC baseline is easy; SOC 0.35 or SOC+δ cuts baseline serve rate 10/12→9/12, and on peak stress **31/40→12/40** with reserve violations under realization.
2. **Charging / depot returns in-horizon?** Depot **returns are frequent** (unload / reposition). **Charging events = 0** in these runs (charge-on-return off; battery not driven to require mid-horizon charge under tested configs).
3. **Limited information vs centralized?** On both baseline and peak-stress **serve rates matched** (10/12 and 31/40). No service-rate coordination gap under the simple claim rule + central registry.
4. **Periodic communication recover loss?** No serve-rate loss to recover on these instances; messages still accrue (138–180). Delay variant changed distance, not serve count.
5. **Active constraints?** Time windows (unserved remain at full SOC); **energy active under low SOC / δ**; payload inactive; charging inactive at defaults; ownership/causality always active.
6. **Casablanca supports the research question?** **Yes for energy-feasible commitments** under plausible SOC/uncertainty—not under default full-SOC release alone. **Not yet for communication-value** on serve rate; a coordination contribution needs harder information regimes or finer metrics (reassignment churn, regret).

## Planning vs realization violations

- Rejected by policy: conservative energy / TW / payload infeasible insertions.  
- Observed under realization: `stress_low_soc` recorded **5 reserve violations** and **2 energy-changed-dispatch** counts — planning δ does not eliminate all realized risk when SOC is tight.

## Negative findings (kept)

- Default release configs do not bind energy.  
- Restricted-info baseline did not reduce serve rate vs full-info greedy on tested scenarios.  
- Depot charging never triggered in the reported runs.  
- RH LNS helps distance slightly on baseline; does not raise serve rate.

## Method note

Baseline B = insertion + relocate LNS with CPU budget (not OR-Tools). Plans validated by simulator feasibility checks. Congestion factor lookup indexed for online path evaluation (same numerical factors as Stage 1).
