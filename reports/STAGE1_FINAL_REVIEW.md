# Stage-1 Final Review (targeted corrections)

Date: 2026-11-07  
Base commit: `6b77e6a`  
Scope: fleet validator, TTI baseline consistency, pinned-boundary protection, binding diagnostic.  
**No Stage-2 algorithms.**

## Verdict

| Item | Result |
| --- | --- |
| Fleet-size enforcement in `validate_schedule` | **PASS** |
| TTI / free-flow baseline consistency | **PASS** (diagnosis + formulation fix) |
| Pinned geography (default verify-only) | **PASS** |
| Baseline energy/payload binding | **Does not bind** (documented limitation) |
| Overall Stage-1 freeze readiness | **Engineering PASS** with explicit scientific limitations |

## 1. Fleet definition enforcement

`validate_schedule` now derives allowed IDs `{V1..Vn}` from `n_vehicles` (optional `vehicle_ids` override) and rejects malformed, unknown, and excess vehicles before reconstruction.

Adversarial tests added: `V99`, too many vehicles under allowlist, empty vehicle ID. Existing positive tiny-graph certification retained.

## 2. Traffic-model baseline

### Mon–Sat diagnosis (no Sunday tuning)

- Workbook free-flow median ≈ **60.0 km/h**
- Closed-form \(A=\mathrm{TTI}\cdot d/60\): MAE **0.24 min**, signed bias ≈ **0**
- Closed-form \(B=\mathrm{TTI}\cdot d/30\): MAE **7.64 min**, signed bias ≈ **+7.6 min**
- Path sample: OSM×TTI / (60×TTI) median ratio ≈ **1.51**

### Formulation adopted

\[
t(e,\tau)=\frac{3.6\,\ell(e)}{60}\cdot f(z,d,h(\tau))
\]

Implemented in `src/race_casablanca/network/travel_time.py` via `edge_tti_baseline_free_flow_s`. OSM class speeds remain for provenance/path context only.

### Sunday holdout (single eval, no tuning)

| Metric | Before (OSM×TTI) | After (60 km/h×TTI) |
| --- | ---: | ---: |
| MAE | 5.91 min | **3.02 min** |
| RMSE | 8.25 min | **4.54 min** |
| Signed bias | (long) | **+1.85 min** |
| Median obs / pred | 6.15 / 9.72 | 6.15 / **6.75** |
| N compared / unique OD | 118 / — | 118 / **104** |

Residual positive bias remains; not claimed as a Waze twin.

## 3. Reproducible geography

- Default `scripts/build_casablanca_boundary.py`: **verify pinned SHA-256 only** (no live APIs)
- Live rebuild: `--force-regenerate` with staging + checksum audit
- Test: `race_source == "geofabrik_pbf"` (removed ineffective `or True`)
- Test: pinned boundary checksums match manifest

Pinned `study_boundary.gpkg` SHA-256: `c003b9edf69b4e8b24b65f2fcc0f4f2e7d2e7ced27148f5d81230f919af31699`

## 4. Validated Casablanca schedule

Scenario: `data/casablanca/scenarios/train/baseline_seed1/`

- Independently certified under hardened validator (incl. fleet IDs)
- 12 pickups, vehicles V1–V3, depot returns
- Total travel ≈ **126.0 km**; min battery after ≈ **26.9 kWh** (reserve 6 kWh)
- First stop path begins: `1849562461 5636182822 5636182821 1849562464 ...` → `457020618` (~12.6 km)

## 5. Constraint-binding diagnostic

Existing certified baselines only (`reports/CONSTRAINT_BINDING_DIAGNOSIS.md`):

| Scenario | Min battery (kWh) | Headroom vs 6 kWh reserve | Max final load (kg) | Payload headroom |
| --- | ---: | ---: | ---: | ---: |
| baseline_seed1 | 26.9 | 20.9 | 107 | 493 |
| baseline_seed4 | 25.4 | 19.4 | 110 | 490 |
| baseline_seed7 | 26.2 | 20.2 | 104 | 496 |
| baseline_seed42 | 27.9 | 21.9 | 91 | 509 |
| baseline_seed202 | 23.0 | 17.0 | 114 | 486 |

**Energy does not bind. Payload does not bind.** Witnesses are offline schedules with full request visibility — not online policy performance.

## 6. Tests

```text
34 passed
```

Includes feasibility adversarial suite (fleet + prior cases), earliest-arrival under TTI baseline, boundary checksum + provenance.

## 7. Remaining limitations (honest)

- Sunday OD still slightly long (+1.85 min mean bias); sample is 118 rows / 104 unique pairs
- No edge-level traffic twin; zonal/hourly TTI only
- Baseline scenarios are not energy-risk stress cases
- No online dispatch environment, EV consumption uncertainty, or multi-agent protocol yet
- Problem formulation for a top-tier algorithmic contribution remains the next intellectual milestone — **before** PPO/GNN architecture work

## Stop line

Targeted Stage-1 corrections complete. Do **not** start Stage-2 algorithms from this checkpoint without an explicit new plan that defines a nontrivial decision problem.
