# Stage 6 — Paper-scope decision

## Options

| Option | Meaning |
| --- | --- |
| A | Methodological optimization paper (novel superior algorithm) |
| B | Applied Casablanca electric-logistics simulation / benchmarking paper |
| C | Benchmark / resource paper |
| D | Additional empirical courier-data collection required for intended claims |

## Evidence summary

1. **Dataset:** hybrid real geography/traffic/demographics + **synthetic** pickups (`STAGE6_DATASET_SCIENTIFIC_VALIDITY.md`). Not “entirely fake”; not “real parcel orders.”
2. **Method:** RACE-RH correctly implemented post–Stage 5.1; Stage 6 paired comparison shows **no advantage** vs greedy charge-to-70% (`STAGE6_FINAL_COMPARISON.md`). Search selects **0** optimized plans; high timeouts (`STAGE6_FAILURE_EXPLANATION.md`).
3. **Sensitivity:** alternate spatial mixtures do not crown RACE-RH (`STAGE6_SENSITIVITY_ANALYSIS.md`).
4. **External courier data:** not available in-repo; partnership would be needed for empirical demand calibration (`STAGE6_HANDOFF.md`).

## Recommendation

**Primary: B — Applied Casablanca electric-logistics simulation and benchmarking paper.**

Honest framing:

- Real published traffic + OSM + HCP covariates.
- Transparent synthetic online EVRP demand.
- Strong charging-policy comparisons (greedy→70% as validated reference).
- Negative methodological result for RACE-RH documented, not hidden.
- Historical FAIL/PARTIAL stages (3C, 4A, 4B, 5, 5.1 Decision B) retained in the narrative.

**Not A:** no demonstrated distinct superior algorithmic contribution.

**C only as a secondary framing:** `casablanca_release_v1` + `evaluation_v1` can be a reusable geographically grounded synthetic resource, but scale and uncalibrated demand limit “flagship benchmark” claims vs large SVRP-style suites.

**D if and only if** the authors insist on claims that require observed courier operations (arrival rates, true customer locations, measured SOC). Those claims are **not** required for a careful B-scope paper.

## Venue honesty

Do **not** assume Transportation Research Part C is justified regardless of results. A methods journal expecting a winning optimizer is a poor fit for Decision B. An applied OR / city logistics / reproducible-benchmark venue matching scope B is more coherent.

## Forbidden claims

- Real-world Casablanca parcel-order dataset.
- Digital-twin travel times.
- RACE-RH superiority over charge-aware greedy / SF-RH.
- That enlarging synthetic episodes alone proves empirical representativeness.
