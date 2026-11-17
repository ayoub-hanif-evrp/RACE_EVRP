# FINAL DATASET VALIDITY (Prompt 3)

## Correct description

**A geographically grounded Casablanca online EV pickup simulation with synthetic demand and modeled vehicle operations.**

Not observed courier trajectory data. Results do not establish real-world fleet deployment performance.

## Provenance layers

| Layer | Status |
|---|---|
| 1. Road-network geometry | Real OSM-derived drive graph (`casablanca_drive.graphml`) |
| 2. Traffic multipliers | Derived / published-style temporal factors on edges (modeled) |
| 3. Population/demographic covariates | Used only where previously documented for scenario generation |
| 4. Customer pickup orders | **Synthetic** |
| 5. Parcel weights, service times, release patterns, demand regimes | **Synthetic** (baseline / peak_stress / tight_windows) |
| 6. Fleet and battery characteristics | Assumed (3 EVs primary; SOC 35%; depot charging) |
| 7. Energy and charging behavior | Simulated model (consumption + depot charge) |

## Locked_final ensemble

Path: `data/casablanca/evaluation_v1/locked_final`

- 30 scenarios: 10 baseline, 10 peak stress, 10 tight-window
- Not used for algorithm development or comparator calibration
- Not regenerated or subsetted after outcomes
- Checksums: `data/casablanca/online_results/final_locked/locked_final_dataset_checksums.json`

## Threats to validity

- Demand assumptions and synthetic release timing
- Network completeness / OSM abstraction
- Traffic temporal variation may not match real Casablanca operations
- Energy-model and depot-charging assumptions
- Small fleet (n=3) primary matrix
- Restricted information boundaries may not match operator practice
- No real operator behavioral calibration
- Scenario dependence of computational load
- Communication delay / loss models are stylized

## Availability

Code, configs, manifests, and locked result tables are versioned in this repository. Reproduction: `scripts/run_race_prompt3_locked_final.py` with `configs/final_locked_manifest.json`.
