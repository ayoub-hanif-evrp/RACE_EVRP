# Casablanca dataset validation

Benchmark: **`casablanca_stage1_5_v1`** · Generator **`0.3.0`**

## Automated checks

Latest full run: **36 passed**.

Covers traffic/FIFO helpers, earliest-arrival, hardened feasibility (coverage, fleet IDs, wrong customer node, shift start), boundary CRS/geography_status/checksums, network connectivity, candidate accessibility.

## Provenance

- Workbook populations: `traffic/communes_workbook.csv`
- HCP measured: `zones/hcp_population_measured_only.csv`
- Demand weights (sole authority): `zones/demand_zone_weights.csv`
- Boundary pins: `manifests/boundary_manifest.json` (LF CSV)
- Freeze: `manifests/benchmark_freeze_casablanca_stage1_5_v1.json`

## Observed build outcomes

| Component | Result |
| --- | --- |
| Traffic workbook | 73,920 trajectory-hour rows; milli-minute units |
| Sunday OD holdout | MAE ~3.02 min (60 km/h TTI baseline); not edge-calibrated |
| Boundary | 15 verified_admin + 7 approximate_study_zone; checksum-pinned |
| Network | 30,943 / 47,787 (largest SCC) |
| Candidates | 46,995 |
| Scenarios | baseline 12 / peak 40 / tight 30 customers; train/val/test seeds |
| Demand weights | 15 measured HCP + 7 commercial-only; 17 eligible zones |

## Acceptance

See `reports/STAGE1_5_HANDOFF.md`.
