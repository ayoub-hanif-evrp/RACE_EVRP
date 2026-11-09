# Stage 6 — Experiment design

**Canonical simulator:** Stage 5.1 (Decision B) online environment.  
**Frozen release:** `casablanca_release_v1` (unchanged scenario IDs).  
**New ensemble:** `casablanca_evaluation_v1` — synthetic expansion from the same generator and frozen geography; **not** new real courier observations.

## Pre-registration (before policy outcomes)

| Item | Choice |
| --- | --- |
| Sampling unit | Independent scenario / episode |
| Not independent | Individual requests inside one episode |
| Release train seeds | Existing 1–8 (baseline/peak/tight as released) |
| Eval_v1 seed ranges | baseline 1101–1108; peak 1201–1208; tight 1301–1308 (`default` tag) |
| Locked final-eval reserve | 2100–2399 (not used for Stage 6 policy comparison) |
| Spatial sensitivity tags | `spatial_pop80`, `spatial_com80`, `spatial_neutral` (hypothetical α/β) |
| SOC suites | `full_soc` (1.0) and `soc35` (0.35) |
| Frozen policies | greedy→70%, greedy adaptive, greedy always-full, SF-RH→70%, SF-RH charge-aware, RACE-RH (negative control) |

## Scripts

| Script | Role |
| --- | --- |
| `scripts/generate_evaluation_ensemble.py` | Build `evaluation_v1/{tag}/` + manifests |
| `scripts/run_stage6_final_comparison.py` | Frozen-policy comparison + paired CIs |
| `scripts/run_stage6_sensitivity.py` | Spatial-mixture sensitivity (greedy→70% vs RACE-RH, peak SOC35) |

## Compute bounds (honest, pre-declared)

RACE-RH is expensive and rarely improves the incumbent (Stage 5.1). Stage 6 therefore:

- Runs all frozen greedy/SF-RH policies on release train + eval_v1 `default`.
- Runs RACE-RH only on `soc35` for release train and the first two peak/tight eval seeds (1201–1202, 1301–1302).
- Skips RACE-RH on baseline eval and on `full_soc` (except via release baseline where it is still skipped for speed except release `soc35`).

These bounds are computational, not cherry-picking after inspecting outcomes for superiority claims.

## Outputs

- `data/casablanca/online_results/stage6_final_comparison.csv`
- `data/casablanca/online_results/stage6_final_comparison_summary.json`
- `data/casablanca/online_results/stage6_sensitivity_spatial.csv`
- Reports: `STAGE6_FINAL_COMPARISON.md`, `STAGE6_SENSITIVITY_ANALYSIS.md`, `STAGE6_FAILURE_EXPLANATION.md`

## Claim discipline

- Eval_v1 increases **experimental power** under fixed synthetic assumptions.
- It does **not** increase the amount of observed parcel demand.
- Paired differences use scenarios as the sampling unit; report mean Δ on-time ± approx. 95% CI.
