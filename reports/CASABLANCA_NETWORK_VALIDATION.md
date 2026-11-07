# Casablanca network validation

## Study boundary

- Definition: union of polygons for the **22 workbook communes**.
- Matching method: OSM administrative features via Overpass name match, Nominatim fill, then workbook OD convex-hull buffers for remaining unmatched names.
- Geography status (audit): **15** `verified_admin`, **7** `approximate_study_zone` — not all 22 are verified official communes.
- Artifacts: `data/casablanca/zones/study_boundary.gpkg`, `zone_crosswalk.csv` / `.gpkg`, `manifests/boundary_manifest.json`.
- **Pinned:** SHA-256 checksums of the committed boundary/crosswalk files are recorded in `boundary_manifest.json`. Rebuilds from live Overpass/Nominatim are non-bit-identical and must not silently overwrite without audit (`scripts/pin_boundary_checksums.py`).

## Drive graph

Construction: `pyrosm` extract from frozen Geofabrik `morocco-260101.osm.pbf`, clipped to the study boundary, simplified, then reduced to the largest weakly connected component and the largest **strongly** connected component so depot-return tours remain feasible under one-way streets.

| Metric | Value |
| --- | --- |
| Pre-WCC nodes / edges | 37,563 / 56,954 |
| Pre-SCC (post-WCC) nodes / edges | 37,487 / 56,895 |
| Post-SCC nodes / edges | **30,943 / 47,787** |
| Nodes / edges excluded by SCC | 6,544 (17.5%) / 9,108 (16.0%) |
| CRS | EPSG:4326 |
| Weak / strong components (final) | 1 / 1 |
| Min / mean / max edge length (m) | 0.58 / 68.08 / 3317.41 |
| Nonpositive lengths | 0 |

Free-flow speeds use OSM `maxspeed` when parseable, else class fallbacks in `configs/travel_time.yaml`. PBF SHA-256 and SCC exclusion stats are recorded in `manifests/network_manifest.json`.

## Congestion model

- Free-flow edge time \(t_0(e)=3.6\cdot \ell(e)/v(e)\).
- Congestion multiplier from workbook TTI: zone×weekday×hour when available, else citywide hourly profile.
- Operational full-week profile: `tti_citywide_hour.csv`. Genuine Sunday OD holdout uses `tti_citywide_hour_fit_mon_sat.csv`.
- This is **not** edge-specific calibration; multipliers are zonal/hourly.
- FIFO: citywide hourly factors exhibit downward jumps; travel-time API applies wait-for-next-hour when waiting improves arrival.

## Turn restrictions

OSMnx drive graphs encode one-way restrictions on edges. Complex relation-level turn bans are not fully enforced by a simple directed MultiDiGraph.

## Figures

- `figures/casablanca_road_network.png`
- `figures/casablanca_congestion_by_hour.png` (workbook-derived citywide TTI)
- `figures/casablanca_od_travel_time_holdout.png` (Mon–Sat fit → Sunday)
