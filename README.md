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

**Not implemented yet:** PPO, GNNs, transformers, MARL, or a final learned RACE architecture.

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
```

Stage 4A post-decision policy: `src/race_casablanca/policies/race_postdecision.py`.  
Stage 4A decision: `reports/STAGE4A_HANDOFF.md`.  
Stage 4B handoff: `reports/STAGE4B_HANDOFF.md`.

## Data layout

```text
data/casablanca/
  raw/                 # downloaded sources (local)
  roads/               # GraphML / GeoPackage network
  traffic/             # processed TTI profiles
  zones/               # study boundary and crosswalk
  pickup_candidates/   # OSM-derived candidates
  scenarios/           # generated requests and witnesses
  fleet/               # vehicle and depot configs
  manifests/           # checksums and provenance
  online_results/      # Stage 2–3B experiment CSVs/JSON
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

## Attribution and licenses

- OpenStreetMap data: © OpenStreetMap contributors, ODbL.
- Casablanca traffic workbook: Rouky & Bousouf, Mendeley Data, DOI 10.17632/8hj76bpzpv.1, CC BY 4.0.
- Population statistics: Haut-Commissariat au Plan (HCP), RGPH 2024.

## Scientific boundary

Synthetic pickup requests are **not** observed Casablanca customer orders. Electric-vehicle energy, depot charging, and package attributes are **modeled assumptions**. Zonal Waze-derived TTI values do **not** provide edge-specific traffic calibration. Reduced initial-SOC experiments are **hypothetical operational stress**, not measured Casablanca fleet SOC.
