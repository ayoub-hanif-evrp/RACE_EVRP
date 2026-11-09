# Stage 6 — Sensitivity analysis (hypothetical assumptions)

All alternatives below are **hypothetical**. They are not calibrated to observed Casablanca parcel counts and are **not** new real-world datasets.

**Runner:** `scripts/run_stage6_sensitivity.py`  
**Results:** `data/casablanca/online_results/stage6_sensitivity_spatial.csv`

## Spatial mixture (α population / β commercial)

Frozen Casablanca geography; regenerate peak seeds 1201–1202 under alternate α/β; compare greedy→70% vs RACE-RH at initial SOC 0.35.

| Tag | Assumed mixture | greedy→70% mean OT (n=2) | RACE-RH mean OT (n=2) |
| --- | --- | ---: | ---: |
| `default` | 60/40 (release assumption) | 0.825 | 0.838 |
| `spatial_pop80` | 80/20 population-dominant | 0.800 | 0.763 |
| `spatial_com80` | 20/80 commercial-dominant | 0.800 | 0.763 |
| `spatial_neutral` | 50/50 | 0.800 | 0.763 |

Notes:

- On `default`, RACE-RH’s two-seed mean is slightly higher only because seed 1202 favors RACE (36/40 vs 32/40); seed 1201 favors greedy (34/40 vs 31/40). This is **not** evidence of superiority.
- Under the three alternative spatial mixtures, greedy→70% is uniformly better on both seeds.
- **Conclusion stability:** charging-readiness / greedy→70% remains competitive; RACE-RH does not become a clear winner under spatial reweighting.

## Other pre-registered sensitivities (documented; not all executed at full scale)

| Factor | Intent | Status in Stage 6 |
| --- | --- | --- |
| Hourly demand profiles | Alternate daytime weights | Documented as needed for manuscript; spatial run prioritized |
| Workload / density | Use existing baseline/peak/tight regimes | Covered in final comparison ensemble |
| Window tightness | tight_windows regime | Covered in final comparison |
| Fleet size | 3-van reference | Held fixed (no expansion) |
| Initial SOC / energy δ | full vs 35% | Covered in final comparison |
| Candidate categories | generic buildings vs informative OSM tags | Not re-pipeline; noted as remaining limitation in validity report |

## Interpretation

Sensitivity evidence does **not** reverse Decision B. It strengthens the claim that results are not an artifact of a single 60/40 draw alone, while confirming that synthetic spatial assumptions still move absolute service rates.
