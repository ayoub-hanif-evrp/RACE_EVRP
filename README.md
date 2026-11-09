# RACE-EVRP — Casablanca online electric pickup research

Reproducible research platform for **online electric parcel pickup** in **Casablanca, Morocco** (`casablanca_release_v1`).

Casablanca is the sole primary geographical research environment. This repository does not use Chinese delivery logs (LaDe, Jilin, or related cities) as demand or calibration data.

## Current stage

| Stage | Status |
| --- | --- |
| 1 — Casablanca benchmark | Frozen release `casablanca_release_v1` |
| 2 / 2.1 — Online EVRP simulator + non-learning baselines | Operational |
| 3A — Communication ablation | Complete; communication **not** selected as primary novelty |
| 3B — Non-learning RACE commitment method | Complete; acceptance **PARTIAL** |
| 3C — Fair mechanism validation | Complete; acceptance **FAIL** for inverse-slack RACE |
| 4A — Post-decision service-capacity pilot | Complete; acceptance **FAIL** (see `reports/STAGE4A_RESEARCH_DECISION.md`) |
| 4B — Charging-and-commitment reformulation | Complete; acceptance **PARTIAL** (see `reports/STAGE4B_HANDOFF.md`) |
| 5 — RACE-RH charging-aware optimizer | Complete; acceptance **PARTIAL** (see `reports/STAGE5_HANDOFF.md`) |
| 5.1 — Optimizer repair + decision gate | Complete; decision **B** — no methodological advantage (see `reports/STAGE5_1_HANDOFF.md`) |
| 6 — Scientific credibility + final evidence | Complete; honest negative for RACE-RH (`reports/STAGE6_HANDOFF.md`) |
| 7 — RACE-COMM (energy-certified selective bidding) | Non-learning milestone complete; provisional go for scale-up (`reports/RACE_METHOD_DECISION.md`) |

**Current method focus:** RACE-COMM task-specific energy-feasible bids + selective messaging (not RACE-RH).  
**RACE-RH:** retained negative control. **MARL/GNN:** deferred until Phase 5 confirms communication value at scale.

## Install

Python 3.11+ required.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## Reproduce

### Stage 1 release integrity

Dependency order: boundary → network → candidates → demand weights → scenarios.

```powershell
.\.venv\Scripts\python scripts\build_casablanca_release.py
.\.venv\Scripts\python scripts\verify_benchmark_release.py --light
.\.venv\Scripts\python -m pytest
```

Full validation (local Morocco PBF): `scripts\verify_benchmark_release.py`.

### Online baselines and RACE (Stages 2–3B)

```powershell
.\.venv\Scripts\python scripts\run_stage2_1_baselines.py
.\.venv\Scripts\python scripts\run_stage3a_communication.py
.\.venv\Scripts\python scripts\run_stage3b_race.py
.\.venv\Scripts\python scripts\run_stage3c_race.py
.\.venv\Scripts\python scripts\run_stage4a_pilot.py
.\.venv\Scripts\python scripts\run_stage4b_exact_toys.py
.\.venv\Scripts\python scripts\run_stage4b_charging_gap.py
.\.venv\Scripts\python scripts\run_stage5_race_rh.py
.\.venv\Scripts\python scripts\run_stage5_1_decision.py
.\.venv\Scripts\python scripts\generate_evaluation_ensemble.py --per-regime 20
.\.venv\Scripts\python scripts\generate_evaluation_ensemble.py --locked --locked-per-regime 10
.\.venv\Scripts\python scripts\run_stage6_credibility_checks.py
.\.venv\Scripts\python scripts\run_stage6_final_comparison.py
.\.venv\Scripts\python scripts\run_stage6_failure_diagnosis.py
.\.venv\Scripts\python scripts\run_stage6_sensitivity.py
```

Stage 4A post-decision policy: `src/race_casablanca/policies/race_postdecision.py`.  
Stage 4A decision: `reports/STAGE4A_HANDOFF.md`.  
Stage 4B handoff: `reports/STAGE4B_HANDOFF.md`.  
Stage 5 RACE-RH: `src/race_casablanca/policies/race_rh.py`, `reports/STAGE5_HANDOFF.md`.  
Stage 5.1 decision: `reports/STAGE5_1_FINAL_METHOD_DECISION.md` (**B**).  
Stage 6: `reports/STAGE6_HANDOFF.md`, evaluation ensemble `data/casablanca/evaluation_v1/`.

## Data layout

```text
data/casablanca/
  raw/                 # downloaded sources (local)
  roads/               # GraphML / GeoPackage network
  traffic/             # processed TTI profiles
  zones/               # study boundary and crosswalk
  pickup_candidates/   # OSM-derived candidates
  scenarios/           # generated requests and witnesses (release v1)
  evaluation_v1/       # Stage 6 synthetic eval ensemble (not new real orders)
  fleet/               # vehicle and depot configs
  manifests/           # checksums and provenance
  online_results/      # Stage 2–6 experiment CSVs/JSON
```

Large raw downloads and heavy GraphML/GeoPackage exports are gitignored; manifests record provenance.

## Key reports

- Stage 1: `reports/STAGE1_RELEASE_HANDOFF.md`
- Stage 2 formulation: `reports/STAGE2_MATHEMATICAL_FORMULATION.md`
- Stage 3A novelty decision: `reports/STAGE3A_NOVELTY_DECISION.md`
- Stage 3B: `reports/STAGE3B_HANDOFF.md`, `STAGE3B_BASELINE_COMPARISON.md`, `STAGE3B_NOVELTY_ASSESSMENT.md`
- Stage 3C: `reports/STAGE3C_HANDOFF.md`, `STAGE3C_RESEARCH_DECISION.md`, `STAGE3C_MECHANISM_ABLATION.md`
- Stage 4A: `reports/STAGE4A_HANDOFF.md`, `STAGE4A_RESEARCH_DECISION.md`, `STAGE4A_EXPERIMENT_RESULTS.md`
- Stage 4B: `reports/STAGE4B_HANDOFF.md`, `STAGE4B_CHARGING_COMMITMENT_PROBLEM.md`, `STAGE4B_CHARGING_DECISION_GAP.md`
- Stage 5: `reports/STAGE5_HANDOFF.md`, `STAGE5_BASELINE_COMPARISON.md`, `STAGE5_NOVELTY_AND_LIMITATIONS.md`
- Stage 5.1: `reports/STAGE5_1_HANDOFF.md`, `STAGE5_1_FINAL_METHOD_DECISION.md`
- Stage 6: `reports/STAGE6_HANDOFF.md`, `STAGE6_DATASET_SCIENTIFIC_VALIDITY.md`, `STAGE6_PAPER_SCOPE_DECISION.md`

## Attribution and licenses

- OpenStreetMap data: © OpenStreetMap contributors, ODbL.
- Casablanca traffic workbook: Rouky & Bousouf, Mendeley Data, DOI 10.17632/8hj76bpzpv.1, CC BY 4.0.
- Population statistics: Haut-Commissariat au Plan (HCP), RGPH 2024.

## Scientific boundary

Synthetic pickup requests are **not** observed Casablanca customer orders. Electric-vehicle energy, depot charging, and package attributes are **modeled assumptions**. Zonal Waze-derived TTI values do **not** provide edge-specific traffic calibration. Reduced initial-SOC experiments are **hypothetical operational stress**, not measured Casablanca fleet SOC.
