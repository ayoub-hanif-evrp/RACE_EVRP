# Stage 6 — Dataset scientific validity

**Release:** `casablanca_release_v1` (generator `0.3.1`)  
**Eval ensemble:** `casablanca_evaluation_v1` (synthetic expansion only)

## Four data categories (do not conflate)

| Category | What it is | What it is not |
| --- | --- | --- |
| 1. Observed/published traffic | Waze-derived OD/hourly congestion (~73,920 trajectory-hour workbook records; citywide TTI profiles) | Courier pickup events |
| 2. Mapped OSM infrastructure | Drive graph + ~47,193 OSM-derived candidate locations (~44,892 accessible) | Observed parcel customers |
| 3. Official HCP covariates | RGPH 2024 population joined to verified_admin zones | Parcel intensity measurements |
| 4. Fully synthetic operations | Request times/windows/weights/service; 3-van depot EV fleet; SOC/δ stress | Real Casablanca courier orders |

**Allowed claim:** reproducible, geographically grounded **synthetic** online EVRP benchmark.  
**Forbidden claim:** real-world Casablanca parcel-order dataset / edge-calibrated digital twin.

## Release inventory (13 scenarios, 368 synthetic requests)

| Split | Scenarios | Requests |
| --- | ---: | ---: |
| Train | 8 | 216 |
| Validation | 2 | 70 |
| Test | 3 | 82 |
| **Total** | **13** | **368** |

## Stage 6 synthetic expansion (not new real observations)

| Ensemble | Scenarios | Requests | Role |
| --- | ---: | ---: | --- |
| `evaluation_v1/default` | 60 (20×3 regimes) | 1640 | Statistical policy comparison |
| `evaluation_v1/locked_final` | 30 (10×3) | 820 | Locked final set — **no policy tuning** |
| Sensitivity tags | spatial_*, hourly_flat, candidates_informative | — | Hypothetical assumption shifts |

The **73,920** traffic rows are not delivery requests. The **47,193** OSM features are candidate locations, not observed customers.

## Documented assumptions (not empirical calibrations)

- Spatial mixture **α=0.6 / β=0.4** (assumed).
- Demand table: 22 zones; only positive-probability zones eligible.
- Generic OSM `building=yes` dominate the sampling frame.
- Seven approximate geographical zones; largest-SCC road filtering.
- Sunday OD holdout: MAE≈3.02 min, bias≈+1.85 min, mean relative error≈49.9% — not a digital twin.
- Hypothetical 3-van fleet, depot, SOC, parcel attributes.

## Credibility checks (complete)

Machine: `data/casablanca/online_results/stage6_credibility_checks.json`.

| Check | Result |
| --- | --- |
| Release snap_node in graph | 368/368; 0 missing |
| Eval default snap/zone | 1640/1640; 0 not-in-graph |
| Locked final snap/zone | 820/820 |
| `is_observed_order` | 0 claimed observed |
| Certified witnesses revalidated | **3/3 valid** (train seeds 1 & 7; test seed 202) |
| Source hashes | recorded for weights + candidates |

## Stale / historical artifacts

| Artifact | Handling |
| --- | --- |
| `constraint_binding_diagnosis.json` | **HISTORICAL** — see `manifests/HISTORICAL_README.md` |
| Absolute Windows paths in older manifests | Prefer relative paths in Stage 6 manifests |

## Model-validation matrix

| Independently checked | Assumed | Unverified |
| --- | --- | --- |
| Checksums, synthetic labels, splits, graph accessibility, certified witnesses | 60/40 mixture, hourly profiles, EV physics, 3-van fleet | Empirical arrival rates, true customer locations, measured van energy |

## Bottom line

Geography/traffic/demographics are genuine external data. Parcel orders are synthetic. Stage 6 increases **evaluation power** under frozen assumptions without claiming new real courier observations.
