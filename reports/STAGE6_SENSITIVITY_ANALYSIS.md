# Stage 6 — Sensitivity analysis (complete; all hypothetical)

**Runner:** `scripts/run_stage6_sensitivity.py`  
**Results:** `stage6_sensitivity_full.csv` (+ `_summary.json`); spatial subset also in `stage6_sensitivity_spatial.csv`.

Nothing below is calibrated to observed Casablanca parcel counts.

## Factors executed

| Factor | Setting | Greedy→70% | RACE-RH | Conclusion shift? |
| --- | --- | ---: | ---: | --- |
| Spatial mixture | default 60/40 (n=4 peak) | 0.838 | 0.831 | No — greedy ≥ RACE |
| Spatial mixture | pop80 / com80 / neutral (n=4 each) | 0.756 | 0.725 | No — greedy better |
| Hourly profile | flat daytime (n=4) | 0.856 | 0.875 | Small RACE mean edge on n=4; not a reversal of the 68-scenario CI |
| Candidate categories | informative OSM only (n=4) | 0.794 | 0.819 | Same caveat (small n) |
| Workload regimes | baseline/peak/tight mix (n=6) | 0.858 | 0.863 | Tie / noise |
| Fleet size | 2 / 3 / 4 vans (n=2 each) | 0.675 / 0.825 / 0.938 | 0.638 / 0.838 / 0.900 | Absolute rates move with fleet; RACE not systematically superior |
| SOC / energy δ | 100%, 50%, 35%, 35%+δ10% | see CSV | see CSV | Charge-to-70% remains competitive; stress lowers absolute OT |

## Interpretation

1. Changing spatial mixture **does** move absolute service rates — synthetic demand assumptions matter.
2. Across the full Stage 6 **paired comparison (n=68)**, RACE-RH remains non-superior to greedy→70%.
3. Small sensitivity cells (n=2–4) can flip local means (e.g. hourly_flat, informative candidates) without overturning the primary CI.
4. Fleet size and SOC are strong operational levers; they are **not** evidence of RACE methodological advantage.

**Decision B stands.** Sensitivities are reported for credibility, not for cherry-picking a winning cell.
