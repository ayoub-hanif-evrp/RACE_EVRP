# Casablanca release audit (`casablanca_release_v1`)

Date: 2026-11-07  
Generator: `0.3.1`  
Pipeline: `scripts/build_casablanca_release.py`

## Acceptance checklist

| Criterion | Result |
| --- | --- |
| Clean rebuild from repaired boundary → network → candidates → weights → scenarios | **PASS** |
| No contradictory certificates / obsolete reference schedules | **PASS** |
| No generator-version mixing; legacy `baseline_seed42` removed | **PASS** |
| Geographic point-in-polygon checks on release requests | **PASS** (`verify_benchmark_release.py`) |
| Demand weights sum to 1; unique zone IDs | **PASS** |
| Physical validation tests | **PASS** (36 pytest) |
| Authoritative release verification | **PASS** (`benchmark_release_verification.json`, full mode) |

## Regenerated artifact counts (actual)

| Artifact | Value |
| --- | ---: |
| Drive nodes / edges (post-SCC) | 30,943 / 47,787 |
| Nodes excluded by SCC | 6,940 (18.3%) |
| Pickup candidates | **47,193** (44,892 accessible) |
| Demand zones | 22 |
| Eligible sampling zones | 17 |
| Positive-weight zones | 16 |
| Ahl Laghlam | accessible candidates > 0 but weight ≈ 0 (commercial+pop zero) — **warning** |

Top weights: Sidi Belyout 16.6%, Hay Hassani 15.1%, El Maarif 12.1%, Sidi Moumen 11.0%, Ain Chock 7.5% (~62% combined). Synthetic, not empirical parcel demand.

## Scenario certificate status

| Scenario | Certified | Witness artifact |
| --- | --- | --- |
| train/baseline_seed1 | true | `reference_schedule.csv` only |
| train/baseline_seed4 | false | `partial_schedule_uncertified.csv` only |
| train/baseline_seed7 | true | `reference_schedule.csv` only |
| test/baseline_seed202 | true | `reference_schedule.csv` only |
| Other release scenarios | unlabeled / uncertified | no obsolete reference schedules |

## Commands

```text
python scripts/build_casablanca_release.py
python scripts/verify_benchmark_release.py --light   # CI-friendly
python scripts/verify_benchmark_release.py           # full, needs PBF+GraphML
python -m pytest
```
