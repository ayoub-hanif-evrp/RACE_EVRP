# Stage-1 scientific correction and validation

Date: 2026-11-06  
Repository commit target: Casablanca Stage-1 correction after independent audit of `0cfff4a`.

## 1. Original issues and fixes

### A. Invalid feasibility witnesses (2 km hop)

**Issue:** `build_feasible_witness()` assumed 2 km/hop, ignored road paths/travel times, often assigned all work to one vehicle, and labeled scenarios feasible without depot return.

**Fix:** Replaced with `race_casablanca.demand.feasibility`:
- directed free-flow paths on the Casablanca MultiDiGraph (correct parallel-edge weights);
- time-dependent evaluation along those paths with explicit waiting policy;
- payload, finish-by-window, energy-to-return, and depot-return checks;
- independent `validate_schedule()` recomputing distance/time/energy/windows from `path_nodes`.

**Result:** `train/baseline_seed1` is **independently certified**:
- 12 requests, 3 vehicles used, 3 depot returns;
- total travel ≈ **122.6 km**;
- min battery after ≈ **24.0 kWh** (reserve 6 kWh);
- validator: `valid=true`, `n_violations=0`.

Impossible/tight cases remain uncertified (`certified_feasible=false`). Labels no longer claim mathematical infeasibility without proof (`stressful_unlabeled`, `tight_windows_unlabeled`).

### B. Broken time-dependent shortest path

**Issue:** NetworkX MultiDiGraph weight callbacks received parallel-edge dicts; weights collapsed to zero. Static departure-time weighting was not a general earliest-arrival algorithm.

**Fix:** Implemented `earliest_arrival()` with:
- explicit parallel-edge enumeration;
- piecewise-constant TTI waiting over hour boundaries (minimize arrival);
- independent DAG exhaustive reference tests.

**Tests:** `tests/test_earliest_arrival.py` — parallel edges, DAG agreement, waiting, disconnects, one-way reachability.

Witness construction uses free-flow path + TD evaluation for scalability; the earliest-arrival oracle remains available for OD validation and unit tests. Certificates claim schedule feasibility, not route optimality.

### C. PBF downloaded but unused

**Issue:** `morocco-260101.osm.pbf` was provenance-only; roads/POIs came from live Overpass.

**Fix:** `pyrosm` extracts roads and candidates from the frozen PBF. Network is simplified, then reduced to the largest strongly connected component for directed tours. Manifest records PBF SHA-256 and method.

**Network (this build):** 30,943 nodes / 47,787 edges; 1 WCC; 1 SCC.

### D. Suspicious zone matches

**Issue:** Al Idrissia→Al Fida and Sidi Maarouf annex match; OD hulls reported as matched communes.

**Fix:** `scripts/audit_zone_matching.py` adds `geography_status`:
- **15 verified_admin** arrondissement matches;
- **7 approximate_study_zone** (OD hulls + audited suspicious matches including Al Idrissia and Sidi Maarouf).

Claim updated: not all 22 zones are verified official communes.

## 2. Additional corrections

| Topic | Change |
| --- | --- |
| Travel-time units | Workbook cells mix minutes and seconds; values >180 normalized to minutes |
| OD validation | Held-out Sunday comparison in minutes (`validate_od_travel_times.py`) |
| HCP provenance | `population_source` = `hcp_rgph2024_matched` or `imputed_household_scaled` |
| Arrival process | Renamed to fixed-count hourly intensity sampling (not NHPP) |
| Fleet relevance | Documented ~170 km usable range; baseline tours ~84–134 km across 3 vehicles |
| Problem class | Explicit depot-only / energy-constrained pickup VRP note |

## 3. Reproduction commands

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python scripts\process_casablanca_traffic.py
.\.venv\Scripts\python scripts\process_hcp_population.py
.\.venv\Scripts\python scripts\audit_zone_matching.py
.\.venv\Scripts\python scripts\build_casablanca_network.py
.\.venv\Scripts\python scripts\build_pickup_candidates.py
.\.venv\Scripts\python scripts\generate_all_scenarios.py
.\.venv\Scripts\python scripts\validate_od_travel_times.py
.\.venv\Scripts\python -m pytest
```

Requires local `data/casablanca/raw/osm/morocco-260101.osm.pbf` (gitignored; MD5/SHA in manifests).

## 4. Actual test results

Executed on this machine after corrections:

```text
22 passed in 5.27s
```

Critical non-skipping checks:
- earliest-arrival parallel-edge / DAG / waiting / disconnect tests;
- feasibility certifies a tiny feasible instance;
- feasibility rejects insufficient-battery and impossible-window instances;
- witness artifacts must include `path_nodes` and `travel_distance_m` (fail if absent).

## 5. Independently validated route example

Scenario: `data/casablanca/scenarios/train/baseline_seed1/`

- Certificate: `graph_constructive_freeflow_path_td_eval_with_depot_return`
- Independent validator: valid
- Vehicles used: V1, V2, V3
- Window definition: service must finish by `tw_end`
- Witness file: `witnesses/reference_schedule.csv` with real `path_nodes` and metre distances

## 6. OD travel-time comparison (held-out Sunday)

After unit normalization:

| Metric | Value |
| --- | --- |
| N compared | 80 |
| Failures | 0 |
| MAE | 69.1 min |
| RMSE | 91.8 min |
| Median abs error | 65.4 min |
| Mean relative error | 0.95 |

Interpretation: the OSM+TTI model is systematically faster than many Waze OD durations. This is reported as a limitation, not a calibration success. Possible causes include optimistic free-flow speeds, citywide/zonal (not edge) congestion, and route disagreement between OSM and Waze. No edge-level twin claim is made.

## 7. Remaining assumptions and Stage-2 readiness

Still assumed / limited:
- synthetic demand spatial mixture (60/40) is a scenario parameter;
- constant Wh/km;
- free-flow path topology inside certificates (TD evaluation along path; not full TD optimal routing in construction);
- approximate study zones retained for unmatched geography;
- OD predictive accuracy remains weak.

**Suitable for Stage 2?** Conditionally closer, but **not fully approved** until:
1. OD travel-time bias is reduced or explicitly scoped out of claims;
2. certificate construction optionally uses full earliest-arrival paths if runtime allows;
3. energy-binding regimes are demonstrated more strongly if energy-risk learning is the novelty.

Stage 2 algorithms should not start from the pre-correction 2 km witnesses.

## 8. Git discipline

Previous history preserved. Correction is a new commit (no rewrite).
