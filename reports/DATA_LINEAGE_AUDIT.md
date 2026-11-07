# Data lineage audit (Stage 1.5)

Benchmark version: `casablanca_stage1_5_v1`  
Generator version: `0.3.0`

## Population sources (separated)

| Artifact | Role |
| --- | --- |
| `data/casablanca/traffic/communes_workbook.csv` | Immutable Mendeley/workbook Table-1 populations |
| `data/casablanca/traffic/communes.csv` | Same workbook table (compatibility); **not** demand authority |
| `data/casablanca/zones/hcp_population_measured_only.csv` | HCP RGPH-2024 measured joins only (NaN if unmatched) |
| `data/casablanca/zones/communes_hcp_joined.csv` | HCP join + documented imputation (modeling reference) |
| `data/casablanca/zones/demand_zone_weights.csv` | **Sole** spatial probability table for scenario generation |

`process_hcp_population.py` no longer overwrites `traffic/communes.csv`.  
`process_casablanca_traffic.py` writes workbook populations only and cannot clobber the demand weight freeze.

## Demand weight policy

Measured HCP population enters the 60% population term **only** when:

1. `geography_status == verified_admin`, and  
2. HCP name match exists in `hcp_population_measured_only.csv`.

Approximate / unmatched zones: population term = 0; commercial buildings still contribute (40% term). Zones with zero accessible candidates are ineligible (`zone_weight` renormalized over eligible zones).

| Count | Value |
| --- | ---: |
| Zones | 22 |
| Measured HCP used | 15 |
| Commercial-only (excluded pop) | 7 |
| Eligible for sampling | 17 |

SHA-256: see `manifests/demand_zone_weights_manifest.json`.

## Generator consumption

`scripts/generate_scenarios.py` loads **only** `demand_zone_weights.csv`. Silent citywide candidate fallback removed: empty zone selection raises.

## Example discrepancy that motivated the freeze

| Zone | Workbook pop (old generator input) | HCP 2024 measured |
| --- | ---: | ---: |
| Anfa | 118,057 | 66,202 |
| Hay Hassani | 140,728 | 537,509 |
| Ain Chock | 147,945 | 374,707 |
| Sidi Moumen | 117,839 | 551,443 |
