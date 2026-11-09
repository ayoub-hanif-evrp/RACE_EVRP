# Stage 6 — Handoff (complete)

**Status:** Complete. Stop method development.  
**Decision:** Paper scope **B**. RACE-RH = documented negative control.

## Completed vs original Stage 6 prompt

| Task | Status |
| --- | --- |
| 1 Dataset validity | Done — `STAGE6_DATASET_SCIENTIFIC_VALIDITY.md` |
| 2 Eval expansion 20/regime + locked set | Done — 60 default + 30 locked_final |
| 3 Sensitivity suite | Done — spatial/hourly/candidates/fleet/SOC/workload |
| 4 Credibility (accessibility + all certified witnesses) | Done — 3/3 witnesses valid |
| 5 Fair frozen-policy comparison | Done — 816 runs / 68 scenarios |
| 6 Matched failure diagnosis | Done — request-level CSV/JSON |
| 7 External validation feasibility | Done — notes below |
| 8 Paper-scope A–D | Done — **B** |

## Key artifacts

- `data/casablanca/evaluation_v1/{default,locked_final,spatial_*,hourly_flat,candidates_informative}/`
- `data/casablanca/online_results/stage6_final_comparison.*`
- `data/casablanca/online_results/stage6_sensitivity_full.*`
- `data/casablanca/online_results/stage6_failure_diagnosis.*`
- `data/casablanca/online_results/stage6_credibility_checks.json`
- `reports/STAGE6_*.md`
- Scripts: `generate_evaluation_ensemble.py`, `run_stage6_*.py`

## Headline numbers

- SOC35 paired RACE − greedy→70%: **−0.010** CI **[−0.019, −0.002]** (n=68)
- RACE mean optimized plans selected: **≈ 0**
- Certified witnesses revalidated: **3/3**

## External validation feasibility

| Source | Status |
| --- | --- |
| Partner anonymized courier logs | Not obtained — needed for demand calibration claims |
| Public traffic/census/OSM | Already used |
| Observed pickups in repo | None — do not fabricate |

Minimum partner fields: anonymized pickup time, approximate zone, weight/volume, service time, daily workload aggregates.

## Reproduce

```powershell
.\.venv\Scripts\python scripts\generate_evaluation_ensemble.py --per-regime 20
.\.venv\Scripts\python scripts\generate_evaluation_ensemble.py --locked --locked-per-regime 10
.\.venv\Scripts\python scripts\run_stage6_credibility_checks.py
.\.venv\Scripts\python scripts\run_stage6_final_comparison.py
.\.venv\Scripts\python scripts\run_stage6_failure_diagnosis.py
.\.venv\Scripts\python scripts\run_stage6_sensitivity.py
```

## STOP

No new heuristics. No neural architectures. No OSM rebuild.  
Next: manuscript under scope B, or a deliberate courier-data partnership (scope D for stronger demand claims only).
