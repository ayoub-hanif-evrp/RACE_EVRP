# Stage 6 — Dataset scientific validity

**Release:** `casablanca_release_v1` (generator `0.3.1`)  
**Commit context:** Stage 6 evidence-building (post Decision B).

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

Regimes: baseline (12 req), peak_stress (40), tight_windows (30). Fleet: 3 hypothetical EVs.

Certified-feasible flags vary by scenario (see `casablanca_dataset_manifest.json`). Online policies must not read witness schedules.

## Documented assumptions (not empirical calibrations)

- Spatial mixture **α=0.6 population / β=0.4 commercial** (assumed; not fit to courier counts).
- Demand table: 22 zones; only zones with positive sampling weight are eligible (`n_eligible_sampling=17` in weights manifest; approximate zones commercial-only).
- Pickup candidates dominated by generic OSM building features — sampling frame, not confirmed customers.
- Largest-SCC road filtering excludes nodes outside the retained strongly connected component (~18% noted in Stage 1 reports).
- Sunday OD holdout travel-time check (`od_travel_time_validation.json`): n_compared=118, MAE≈3.02 min, signed bias≈+1.85 min, mean relative error≈49.9%. Useful for time-dependent routing conditions; **not** precise road-level twin accuracy.
- EV energy/charging/depot: configured hypothetical parameters.

## Stale / historical artifacts (do not treat as current)

| Artifact | Issue | Handling |
| --- | --- | --- |
| `constraint_binding_diagnosis.json` | Legacy seed-42 / seed-4 certification narrative may disagree with active `casablanca_release_v1` split rules | **Historical diagnostic only** — not the active release authority |
| Absolute Windows paths in some manifests | Portability noise | Prefer relative `data/casablanca/...` paths in new Stage 6 manifests |

Active authority: `casablanca_dataset_manifest.json` + per-scenario `scenario_metadata.json` under `scenarios/{train,validation,test}/`.

## Model-validation matrix

| Check | Status |
| --- | --- |
| Source checksums / generator version freeze | Done (release manifests) |
| Synthetic labeling / claim discipline | Done |
| Train/val/test seed splits | Done |
| Accessibility filter on candidates | Done |
| Hard-deadline + conservative energy in online sim | Done (Stages 4B–5.1) |
| Empirical parcel arrival-rate calibration | **Missing** |
| Observed customer-location validation | **Missing** |
| Measured van energy / charge curves | **Missing** |
| Broad independent scenario ensemble | Added as `casablanca_evaluation_v1` (Stage 6; synthetic expansion, not new real observations) |
| Release request field completeness | Stage 6 check: 368/368 have `snap_node` + `declared_zone_id`; `is_observed_order=False` |
| Eval_v1 default request completeness | Stage 6 check: 656/656 have snap + zone; all synthetic labels |

Machine check: `data/casablanca/online_results/stage6_credibility_checks.json`.

## Bottom line

The geography/traffic/demographics foundations are genuine external data. Parcel orders are synthetic. Scale (13 release scenarios) is small for strong generalization; Stage 6 expands **evaluation episodes** from the frozen generator without claiming new real courier data.
