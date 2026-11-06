# Casablanca synthetic demand generation

## Pickup candidates

- Source: OSM POIs/buildings (`shop`, `office`, selected `amenity`, commercial/residential `building`) inside the study boundary.
- Count: **25,341** candidates; **25,220** accessible after snap (`rejection_rate ≈ 0.48%`).
- Median snap distance (accessible): **34.9 m** (threshold 150 m).
- Zone assignment: spatial join to matched commune polygons / OD-hull fallbacks.

## Generator

- Version: `0.1.0` (`configs/demand_default.yaml`).
- Spatial weights: mixture of HCP-joined population (or household-scaled placeholder) and workbook commercial-building counts.
- Temporal: nonhomogeneous Poisson-style hour sampling from declared intensity profiles, uniform within hour.
- Package/service/window parameters are regime-declared, not observed orders.

## Regimes

| Regime | Customers | Window (h) | Feasible mode | Label |
| --- | --- | --- | --- | --- |
| `baseline_feasible` | 40 | 2.0 | yes (witness written) | baseline |
| `peak_stress` | 80 | 1.5 | no | stressful |
| `partially_infeasible` | 60 | 1.0 | no | partially_infeasible |

## Depot

One accessible OSM-derived scenario depot near the candidate median location (`data/casablanca/fleet/depot.json`). Explicitly **not** a claimed real logistics hub.

## Splits (fixed before tuning)

- Train seeds: 1–8
- Validation seeds: 101–102
- Test seeds: 201–203

Generated via `scripts/generate_all_scenarios.py` (13 scenarios). Feasible-mode witnesses live under `scenarios/.../witnesses/` and must not be read by online policies.

## Claim

Requests are **synthetic geographically grounded pickups**, not observed Casablanca customer orders.
