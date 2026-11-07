# Reproducibility freeze (Stage 1.5)

## Benchmark identifier

**`casablanca_stage1_5_v1`**

## Line-ending policy

`.gitattributes` forces LF for CSV/JSON/MD/YAML/Python.  
Pinned `zone_crosswalk.csv` is stored and hashed as LF:

| Artifact | SHA-256 |
| --- | --- |
| `zone_crosswalk.csv` | `dcf6516e1c4d67b70a5c49a85412397fa08c23a45a23aad6bfebe87658ff4cd0` |
| `study_boundary.gpkg` | `d6ef82b9be909c2be2610421b0dc3c6271094abf973dbbd156fa3cf469eab551` |
| `zone_crosswalk.gpkg` | `4f26b08debfeb59d3dac3a944398c6c6c4116286ce2c91e15db5f13b6ac7d615` |
| `demand_zone_weights.csv` | see `demand_zone_weights_manifest.json` |

Default `scripts/build_casablanca_boundary.py` verifies pins; live regenerate requires `--force-regenerate`.

## Portable paths

New/updated checksum metadata uses project-relative paths (`data/casablanca/...`), not machine-absolute Windows paths.

## Dataset facts (synced)

| Item | Value |
| --- | --- |
| Generator | 0.3.0 |
| Benchmark | casablanca_stage1_5_v1 |
| Baseline / peak / tight customers | 12 / 40 / 30 |
| Pickup candidates | 46,995 |
| Train / val / test seeds | 8+1 / 2 / 3 (plus optional baseline_seed42) |
| Verified admin / approximate zones | 15 / 7 |

## Traffic model limit

Sunday OD holdout remains a zonal/citywide TTI approximation on a 60 km/h baseline (MAE ~3 min). Not an edge-level Casablanca twin. Closed-form 0.24 min Mon–Sat error is internal TTI consistency, not independent validation.
