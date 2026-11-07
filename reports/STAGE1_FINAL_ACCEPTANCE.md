# Stage-1 Final Scientific Acceptance

Date: 2026-11-07  
Scope: Tasks 1–3 only (validator hardening, traffic units + Sunday OD holdout, geography pin + SCC).  
**No Stage-2 algorithms** (no RL, simulators, or neural architectures).

## Verdict summary

| Task | Verdict | Notes |
| --- | --- | --- |
| 1 — Feasibility validator | **PASS** | Coverage, returns, timestamp reconstruction, release checks; adversarial suite green |
| 2 — Traffic units + Sunday holdout | **CONDITIONAL PASS** | Units corrected (milli-minutes); genuine Mon–Sat→Sunday OD MAE ≈ 5.9 min; residual bias remains; not edge-calibrated |
| 3 — Geographic reproducibility | **PASS** | Boundary SHA-256 pinned; geography_status explicit; pre/post SCC counts recorded |
| **Overall Stage-1 closure** | **CONDITIONAL PASS** | Ready to stop before Stage 2; OD model is usable for zonal/hourly congestion but not claimed as a Waze twin |

## Task 1 — Feasibility validator

`validate_schedule()` now fails unless every request appears exactly once, returns end at `depot_node`, paths/edges are continuous, reconstructed timestamps match within `1e-3` min, `service_start ≥ release_min`, and payload/battery/reserve/energy/time conservation hold.

### pytest (feasibility)

```text
tests/test_feasibility_witness.py ...........                     [100%]
11 passed in 0.50s
```

Adversarial cases that must fail (and do): empty schedule vs non-empty requests; missing/duplicate pickup; fabricated/wrong return; broken path/missing edge; altered timestamps; service before release. Positive tiny-graph certified case retained.

### Full suite

```text
30 passed
```

### Validated Casablanca schedule path

Scenario: `data/casablanca/scenarios/train/baseline_seed1/`

- `certified_feasible: true` under the stricter independent validator
- 12 requests, vehicles V1–V3, 3 depot returns
- total travel ≈ **136.1 km**; min battery after ≈ **26.3 kWh**
- first stop: depot `1849562461` → `457020618`, distance ≈ 12.99 km
- `path_nodes` begins: `1849562461 5636182822 5636182821 1849562464 ...` (full path in `witnesses/reference_schedule.csv`)

### Corrupted-schedule rejection evidence

On the tiny certified schedule, deliberate corruptions yield `valid=False`:

| Corruption | `valid` |
| --- | --- |
| Empty schedule vs 2 requests | False (`empty_schedule`) |
| Missing pickup `r0` | False |
| Return `to_node` ≠ depot | False |
| `planned_arrival_min` +5 min vs reconstruction | False |
| Unmodified certified schedule | True |

## Task 2 — Traffic units and Sunday OD holdout

### Unit audit

Workbook headers say minutes. ~57% of Tue–Sun cells are integers >180. Interpreting those as **seconds (/60)** gives ~1.5 km/h median speeds (invalid). Interpreting as **minutes×1000 (/1000)** yields:

- median travel ≈ 7.0 min
- median speed ≈ 24.9 km/h
- median free-flow ≈ **60.0 km/h** (matches workbook TTI definition)
- 100% of rows in 5–120 km/h after correction

Parser: `_normalize_travel_time_min` in `src/race_casablanca/traffic/workbook.py`; dynamic COMMUNE header detection for Tue–Sun sheets.

### Genuine holdout design

- Fit citywide TTI on **Mon–Sat only** → `tti_citywide_hour_fit_mon_sat.csv`
- Operational full-week profile retained → `tti_citywide_hour.csv`
- Predict **Sunday** OD durations with fit profile only → `od_travel_time_holdout_sunday.csv`

| Metric | Value |
| --- | --- |
| N sampled / compared | 120 / 118 |
| Snap failures | 0 |
| Collapsed OD (`o_node == d_node`) | 2 |
| MAE | **5.91 min** |
| RMSE | **8.25 min** |
| Median abs error | 3.99 min |
| Peak 07–10 MAE | 5.99 min |
| Median obs / pred | 6.15 / 9.72 min |

**Limitation (why CONDITIONAL):** mean relative error ≈ 1.0 and median prediction still longer than median observation on this OSM free-flow + citywide TTI stack. No edge-level calibration; Waze routes ≠ OSM paths. Residual is reported honestly, not tuned away.

## Task 3 — Geographic reproducibility

### Pinned study geography

Committed artifacts are authoritative. Live Overpass/Nominatim rebuilds are non-bit-identical and must not silently overwrite.

| Artifact | SHA-256 |
| --- | --- |
| `study_boundary.gpkg` | `c003b9edf69b4e8b24b65f2fcc0f4f2e7d2e7ced27148f5d81230f919af31699` |
| `zone_crosswalk.gpkg` | `ae781a13675c1bc786e71e1c0c8900d188f2e4f391cdb98bbfb9fd9e4dba528c` |
| `zone_crosswalk.csv` | `83fea5db99309038bcafc737394d971d54f580e8d4c9dc3a4627531226bd7045` |

Recorded in `data/casablanca/manifests/boundary_manifest.json` via `scripts/pin_boundary_checksums.py`.

### Zone status (not all 22 verified communes)

- **15** `verified_admin`
- **7** `approximate_study_zone` (OD hulls + audited suspicious matches)

### SCC exclusion (network build)

From `network_manifest.json` after PBF extract:

| Stage | Nodes | Edges |
| --- | --- | --- |
| Pre-WCC | 37,563 | 56,954 |
| Post-WCC / pre-SCC | 37,487 | 56,895 |
| Post-SCC (retained) | **30,943** | **47,787** |
| Excluded by SCC | 6,544 (17.5%) | 9,108 (16.0%) |

Final graph is strongly connected for depot-return tours under one-ways.

## Stop line

Stage-1 scientific acceptance for the three blockers is closed under **CONDITIONAL PASS** (Task 2 residual OD bias). Do **not** start event-driven EVRP simulators, PPO, GNN, or other Stage-2 method work from this checkpoint without an explicit new plan.
