# RACE-EVRP — Casablanca Stage 1

Reproducible research benchmark for **online electric parcel pickup** in **Casablanca, Morocco**.

Casablanca is the sole primary geographical research environment. This repository does not use Chinese delivery logs (LaDe, Jilin, or related cities) as demand or calibration data.

Stage 1 builds:

- a directed OpenStreetMap driving network for a documented Casablanca study area;
- a time-dependent travel-time model calibrated only to published zonal/hourly Waze-derived congestion where justified;
- synthetic but geographically grounded pickup scenarios with explicitly labeled electric-fleet assumptions.

Stage 1 does **not** implement PPO, GNNs, or the full multi-agent EVRP simulator.

## Install

Python 3.11+ required.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## Reproduce Stage 1

```powershell
.\.venv\Scripts\python scripts\download_casablanca_traffic.py
.\.venv\Scripts\python scripts\download_morocco_osm.py
.\.venv\Scripts\python scripts\download_hcp_population.py
.\.venv\Scripts\python scripts\process_casablanca_traffic.py
.\.venv\Scripts\python scripts\process_hcp_population.py
.\.venv\Scripts\python scripts\build_casablanca_boundary.py
.\.venv\Scripts\python scripts\audit_zone_matching.py
.\.venv\Scripts\python scripts\build_casablanca_network.py
.\.venv\Scripts\python scripts\build_pickup_candidates.py
.\.venv\Scripts\python scripts\generate_all_scenarios.py
.\.venv\Scripts\python scripts\validate_od_travel_times.py
.\.venv\Scripts\python scripts\write_dataset_manifest.py
.\.venv\Scripts\python scripts\make_casablanca_figures.py
.\.venv\Scripts\python -m pytest
```

Roads and pickup candidates are extracted from the frozen Geofabrik `morocco-260101.osm.pbf` snapshot (not live Overpass). Feasible labels require independently validated graph schedules; see `reports/STAGE1_SCIENTIFIC_CORRECTION.md`.


Large raw downloads (OpenStreetMap PBF, census Excel, traffic workbook) and heavy GraphML/GeoPackage exports are fetched or rebuilt by scripts and recorded in manifests. Oversized binaries are gitignored.

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
```

## Reports

- `reports/CASABLANCA_DATA_SOURCES.md`
- `reports/CASABLANCA_TRAFFIC_AUDIT.md`
- `reports/CASABLANCA_NETWORK_VALIDATION.md`
- `reports/CASABLANCA_DEMAND_GENERATION.md`
- `reports/CASABLANCA_ENERGY_ASSUMPTIONS.md`
- `reports/CASABLANCA_DATASET_VALIDATION.md`
- `reports/CASABLANCA_RESEARCH_METHOD.md`
- `reports/STAGE1_CASABLANCA_HANDOFF.md`

## Attribution and licenses

- OpenStreetMap data: © OpenStreetMap contributors, ODbL.
- Casablanca traffic workbook: Rouky & Bousouf, Mendeley Data, DOI 10.17632/8hj76bpzpv.1, CC BY 4.0.
- Population statistics: Haut-Commissariat au Plan (HCP), RGPH 2024.

## Scientific boundary

Synthetic pickup requests are **not** observed Casablanca customer orders. Electric-vehicle energy, depot charging, and package attributes are **modeled assumptions**. Zonal Waze-derived TTI values do **not** provide edge-specific traffic calibration.
