# Stage 6 — Handoff

**Status:** Complete. Stop method development.  
**Decision:** Paper scope **B** (applied Casablanca EV logistics simulation / benchmarking) with RACE-RH as documented **negative control**. See `STAGE6_PAPER_SCOPE_DECISION.md`.

## Deliverables

| Path | Role |
| --- | --- |
| `reports/STAGE6_DATASET_SCIENTIFIC_VALIDITY.md` | Provenance / hybrid-data validity |
| `reports/STAGE6_EXPERIMENT_DESIGN.md` | Pre-registered eval design |
| `reports/STAGE6_SENSITIVITY_ANALYSIS.md` | Spatial mixture sensitivity |
| `reports/STAGE6_FINAL_COMPARISON.md` | Frozen-policy comparison |
| `reports/STAGE6_FAILURE_EXPLANATION.md` | Why RACE-RH fails |
| `reports/STAGE6_PAPER_SCOPE_DECISION.md` | Scope A–D recommendation |
| `scripts/generate_evaluation_ensemble.py` | `casablanca_evaluation_v1` builder |
| `scripts/run_stage6_final_comparison.py` | Comparison runner |
| `scripts/run_stage6_sensitivity.py` | Sensitivity runner |
| `scripts/run_stage6_credibility_checks.py` | Inventory / claim checks |
| `data/casablanca/evaluation_v1/` | Synthetic ensemble (default + spatial_*) |
| `data/casablanca/online_results/stage6_*.csv/json` | Machine-readable results |
| `data/casablanca/manifests/HISTORICAL_README.md` | Marks stale diagnostics |

## External validation feasibility (Task 7)

| Source | Feasible now? | Use |
| --- | --- | --- |
| Partner anonymized courier logs (time, zone, weight/volume, service, daily workload) | **Unknown / not obtained** | Would enable demand calibration; do **not** fabricate |
| Public aggregates (traffic, census, OSM) | Yes (already used) | Geography/traffic covariates only |
| Individual observed pickups in this repo | **No** | Paper must state synthetic demand |

Minimum useful partner fields: anonymized pickup time, approximate origin zone, parcel weight or volume, service duration, aggregate daily workload.

## Reproduce Stage 6

```powershell
.\.venv\Scripts\python scripts\generate_evaluation_ensemble.py
.\.venv\Scripts\python scripts\run_stage6_credibility_checks.py
.\.venv\Scripts\python scripts\run_stage6_final_comparison.py
.\.venv\Scripts\python scripts\run_stage6_sensitivity.py
```

Locked final-evaluation seeds **2100–2399** remain unused (no policy tuning on them).

## STOP

- No new RACE heuristics.
- No PPO/GNN/MARL.
- No OSM/census rebuild.
- Next work: **manuscript writing** under scope B, or a deliberate partnership to obtain real operational data (scope D for stronger demand claims only).
