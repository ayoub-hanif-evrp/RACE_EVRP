# Casablanca network validation (`casablanca_release_v1`)

## Study boundary

- 15 `verified_admin` + 7 `approximate_study_zone`
- Pinned SHA-256 verified by default (`build_casablanca_boundary.py`)
- Al Idrissia / Sidi Maarouf: OD-hull approximate study areas (incorrect admin matches rejected)

## Drive graph (rebuilt after boundary repair)

| Metric | Value |
| --- | ---: |
| Post-SCC nodes / edges | 30,943 / 47,787 |
| Pre-SCC nodes / edges | 37,883 / 57,429 |
| Nodes excluded by SCC | 6,940 (18.3%) |
| Weak / strong components (final) | 1 / 1 |

Source: frozen `morocco-260101.osm.pbf` via pyrosm. Edge zone labels recomputed from corrected polygons.

## Congestion

Uses TTI × (length / 60 km/h), not OSM-class free-flow × TTI. See `CASABLANCA_FINAL_DATASET_METHOD.md`.

## Candidates

47,193 mapped OSM places; 44,892 accessible. Not verified parcel customers.
