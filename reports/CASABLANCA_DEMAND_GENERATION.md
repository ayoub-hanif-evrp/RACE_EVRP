# Casablanca synthetic demand generation

Authoritative method for release **`casablanca_release_v1`** / generator **`0.3.1`**.  
See also `CASABLANCA_FINAL_DATASET_METHOD.md`.

## Pickup candidates

- Source: OSM features inside the study boundary (`shop`, `office`, `amenity`, selected `building` tags), extracted from the frozen Geofabrik PBF.
- Regenerated count: **47,193** candidates; **44,892** accessible after snap (threshold 150 m).
- Category mix is dominated by generic `building=*` (~87%); these are mapped places, **not** verified parcel customers.
- Zone assignment: point-in-polygon to zone polygons with `verified_admin` preferred on overlaps.

## Generator

- Version: `0.3.1` (`configs/demand_default.yaml`).
- Spatial probabilities: **only** `data/casablanca/zones/demand_zone_weights.csv`.
- Population term (60%): HCP RGPH-2024 measured values solely for `verified_admin` + HCP-matched zones.
- Commercial term (40%): workbook commercial-building counts.
- Approximate / unmatched zones: commercial-only (population contribution 0).
- Temporal: fixed-count hourly intensity sampling (not NHPP).
- Empty-zone citywide fallback: **removed** (fail / renormalize eligible zones).

## Regimes

| Regime | Customers | Start hour | Window (h) | Certificate attempt |
| --- | ---: | ---: | ---: | --- |
| `baseline` | 12 | 8 | ~3.0 | yes (independent validator) |
| `peak_stress` | 40 | 7 | ~1.5 | no (unlabeled stress) |
| `tight_windows` | 30 | 8 | ~1.0 | no (unlabeled) |

## Splits

- Train seeds: 1–8  
- Validation: 101–102  
- Test: 201–203  
- Legacy seed 42: **excluded** from release  

## Claim

Requests are **synthetic geographically grounded pickups**, not observed Casablanca customer orders.
