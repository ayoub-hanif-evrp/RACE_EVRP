# Geographic coverage audit (Stage 1.5)

## Zone status (22 workbook communes)

| Status | Count | Meaning |
| --- | ---: | --- |
| `verified_admin` | 15 | OSM admin polygon name-match retained |
| `approximate_study_zone` | 7 | OD convex-hull study area (not official commune) |

## Repaired incorrect polygons

| Zone | Prior issue | Repair |
| --- | --- | --- |
| Al Idrissia | Nominatim geometry referenced Al Fida | Replaced with OD convex-hull study area |
| Sidi Maarouf | Suspicious annex Nominatim match | Replaced with OD convex-hull study area |

Repairs: `scripts/repair_suspicious_zone_geometries.py` (no live Overpass).  
Default boundary script verifies pinned SHA-256 only.

## Demand sampling geography

- Requests declare `declared_zone_id` / `commune` equal to the sampled weight zone.
- Candidate must belong to that commune; no silent all-city redraw.
- 17/22 zones have ≥1 accessible candidate on the retained SCC network.

## Strongly connected component (road network)

From `network_manifest.json`:

| Stage | Nodes | Edges |
| --- | ---: | ---: |
| Pre-SCC | 37,487 | 56,895 |
| Post-SCC retained | 30,943 | 47,787 |
| Excluded | 6,544 (17.5%) | 9,108 (16.0%) |

Pickups outside the largest SCC are inaccessible by construction; demand eligibility uses accessibility flags.

## Remaining limitations

- Approximate zones are justified study areas, not inventing official boundaries.
- Zone polygons may overlap at edges; candidates carry a single commune label from the build join.
- Network rebuild after hull repair was not required for certificate regeneration in this freeze (commune labels already on candidates).
