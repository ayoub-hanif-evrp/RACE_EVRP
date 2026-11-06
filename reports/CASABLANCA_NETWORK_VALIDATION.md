# Casablanca network validation

## Study boundary

- Definition: union of polygons for the **22 workbook communes**.
- Matching method: OSM administrative features via Overpass name match, Nominatim fill, then workbook OD convex-hull buffers for remaining unmatched names.
- Result in this build: **17** trusted OSM admin matches, **5** documented OD-hull fallbacks (`Echchallalate`, `Bou Chentouf`, `Lissasfa`, `Ahl Laghlam`, `Moulay Youssef`).
- Artifacts: `data/casablanca/zones/study_boundary.gpkg`, `zone_crosswalk.csv`, `manifests/boundary_manifest.json`.

## Drive graph

| Metric | Value |
| --- | --- |
| Nodes | 37,952 |
| Edges | 100,286 |
| CRS | EPSG:4326 |
| Weak components | 1 (fully weakly connected) |
| Strong components | 153 (largest 37,764 nodes) |
| Min / mean / max edge length (m) | 0.58 / 67.87 / 4247.29 |
| Nonpositive lengths | 0 |

Construction: OSMnx `graph_from_polygon` with `network_type="drive"`, `simplify=True`, `retain_all=False`, `truncate_by_edge=True`. True OSM junctions retained after simplification. Free-flow speeds use OSM `maxspeed` when parseable, else class fallbacks in `configs/travel_time.yaml`.

Geofabrik `morocco-260101.osm.pbf` (MD5 verified) is retained as the archived Morocco extract. Network construction for Stage 1 uses the clipped study-area Overpass query for reproducibility of the directed graph inside the matched boundary.

## Congestion model

- Free-flow edge time \(t_0(e)=3.6\cdot \ell(e)/v(e)\).
- Congestion multiplier from workbook TTI: zone×weekday×hour when available, else citywide hourly profile.
- This is **not** edge-specific calibration; multipliers are zonal/hourly.
- FIFO: citywide hourly factors exhibit downward jumps; travel-time API applies wait-for-next-hour when waiting improves arrival.

## Turn restrictions

OSMnx drive graphs encode one-way restrictions on edges. Complex relation-level turn bans are not fully enforced by a simple directed MultiDiGraph.

## Figures

- `figures/casablanca_road_network.png`
- `figures/casablanca_congestion_by_hour.png` (workbook-derived citywide TTI)
