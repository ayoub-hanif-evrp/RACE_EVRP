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
| Eval_v1 seed ranges | baseline 1101–1120; peak 1201–1220; tight 1301–1320 (`default` tag; **20/regime**) |
| Locked final-eval set | Materialized under `evaluation_v1/locked_final` (10/regime: 2101–2110, 2201–2210, 2301–2310); **no policy tuning** |
| Sensitivity tags | `spatial_*`, `hourly_flat`, `candidates_informative` (all hypothetical) |
| SOC suites | `full_soc` (1.0) and `soc35` (0.35) |
| Frozen policies | greedy→70%, greedy adaptive, greedy always-full, SF-RH→70%, SF-RH charge-aware, RACE-RH (negative control) |

## Scripts

| Script | Role |
| --- | --- |
| `scripts/generate_evaluation_ensemble.py` | Build `evaluation_v1/{tag}/` + locked_final + manifests |
| `scripts/run_stage6_final_comparison.py` | Fair frozen-policy comparison + paired CIs (checkpoint/resume) |
| `scripts/run_stage6_sensitivity.py` | Spatial/hourly/fleet/SOC/candidate sensitivity |
| `scripts/run_stage6_credibility_checks.py` | Accessibility + certified witness revalidation |
| `scripts/run_stage6_failure_diagnosis.py` | Matched request-level greedy vs RACE traces |

## Fairness (complete Stage 6)

- **All** frozen policies on **all** release-train + `evaluation_v1/default` scenarios (60 eval + 8 release).
- Both `full_soc` and `soc35` suites.
- `locked_final` is never used for policy comparison or selection.
- Checkpoint resume allowed for compute reliability; no post-hoc scenario dropping.

## Outputs

- `data/casablanca/online_results/stage6_final_comparison.csv` (816 runs)
- `data/casablanca/online_results/stage6_final_comparison_summary.json`
- `data/casablanca/online_results/stage6_sensitivity_full.csv`
- `data/casablanca/online_results/stage6_failure_diagnosis.json`
- `data/casablanca/online_results/stage6_credibility_checks.json`
- Reports: all `STAGE6_*.md`

## Claim discipline

- Eval_v1 increases **experimental power** under fixed synthetic assumptions.
- It does **not** increase the amount of observed parcel demand.
- Paired differences use scenarios as the sampling unit; report mean Δ on-time ± approx. 95% CI.
