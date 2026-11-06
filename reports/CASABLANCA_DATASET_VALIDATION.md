# Casablanca dataset validation

## Automated checks

`pytest` covers:

- traffic workbook commune count, trajectory-hour coverage, FIFO helper;
- travel-time nonnegativity and waiting policy;
- seeded demand reproducibility;
- boundary CRS / non-empty geometry;
- directed network lengths, connectivity, free-flow times;
- pickup snap accessibility rates;
- fleet/package bounds, witness energy reserve, train/val/test seed isolation;
- depot scenario-only labeling.

## Provenance artifacts

Manifests under `data/casablanca/manifests/` record retrieval UTC, URLs, hashes, and build summaries for traffic, OSM, HCP, boundary, network, candidates, scenarios, and the top-level `casablanca_dataset_manifest.json`.

## Observed build outcomes

| Component | Result |
| --- | --- |
| Traffic workbook | SHA verified; 73,920 trajectory-hour rows |
| Morocco PBF | MD5 verified (240,265,932 bytes) |
| HCP join | 16/22 direct matches; 6 household-scaled placeholders |
| Boundary | 22/22 zones represented (17 OSM admin + 5 OD hulls) |
| Network | 37,952 nodes / 100,286 edges; weakly connected |
| Candidates | 25,341; 99.5% accessible |
| Scenarios | 13 (8 train / 2 val / 3 test) |
| Feasible witnesses | share_within_window = 1.0 on baseline seeds checked |

## Large local-only files

Gitignored (rebuild from scripts): Morocco PBF, GraphML/GeoPackage road exports, candidate GeoPackage. Manifests, configs, CSVs, reports, and figures are retained in-repo when size allows.
