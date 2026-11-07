# Casablanca dataset validation

## Automated checks

`pytest` covers:

- traffic workbook commune count, trajectory-hour coverage, FIFO helper;
- travel-time nonnegativity and waiting policy;
- seeded demand reproducibility;
- boundary CRS / non-empty geometry / geography_status;
- directed network lengths, connectivity, free-flow times;
- pickup snap accessibility rates;
- fleet/package bounds, witness energy reserve, train/val/test seed isolation;
- depot scenario-only labeling;
- hardened feasibility validator adversarial suite.

Latest full run: **30 passed**.

## Provenance artifacts

Manifests under `data/casablanca/manifests/` record retrieval UTC, URLs, hashes, and build summaries for traffic, OSM, HCP, boundary, network, candidates, scenarios, OD holdout, and the top-level `casablanca_dataset_manifest.json`.

Boundary artifacts are **SHA-256 pinned** in `boundary_manifest.json`; live Overpass/Nominatim rebuilds must not silently overwrite them.

## Observed build outcomes

| Component | Result |
| --- | --- |
| Traffic workbook | SHA verified; 73,920 trajectory-hour rows; milli-minute unit rule |
| Mon–Sat→Sunday OD holdout | MAE 5.91 min / RMSE 8.25 min (118 compared; 2 collapsed OD) |
| Morocco PBF | MD5/SHA verified |
| HCP join | 16/22 direct matches; 6 household-scaled placeholders |
| Boundary | 22 zones; 15 `verified_admin` + 7 `approximate_study_zone`; checksums pinned |
| Network | 30,943 nodes / 47,787 edges (largest SCC); 17.5% nodes excluded by SCC filter |
| Candidates | OSM-derived from frozen PBF; accessibility checked |
| Scenarios | 14 dirs (incl. baseline_seed42) / 13 split-plan seeds; baselines independently certified |

## Large local-only files

Gitignored (rebuild from scripts): Morocco PBF, GraphML/GeoPackage road exports, candidate GeoPackage. Manifests, configs, CSVs, reports, and figures are retained in-repo when size allows.

## Acceptance

See `reports/STAGE1_FINAL_ACCEPTANCE.md` for PASS / CONDITIONAL PASS by task.
