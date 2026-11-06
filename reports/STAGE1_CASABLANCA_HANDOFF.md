# Stage-1 Casablanca handoff

## What was delivered

- LaDe/Jilin artifacts removed; package retargeted to `race_casablanca`.
- Published Casablanca traffic workbook audited and converted to TTI profiles.
- Morocco OSM extract downloaded and checksum-verified.
- HCP RGPH-2024 population joined where names match.
- Study boundary = union of 22 workbook zones (17 OSM admin + 5 OD-hull fallbacks).
- Directed OSM drive graph with free-flow + zonal/hourly congestion API (FIFO wait policy).
- OSM pickup candidates, seeded regimes, depot/fleet YAML, train/val/test scenarios, feasible witnesses.
- Eight reports, two publication figures, pytest suite, manifests.

## Reproduce

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python scripts\download_casablanca_traffic.py
.\.venv\Scripts\python scripts\download_morocco_osm.py
.\.venv\Scripts\python scripts\download_hcp_population.py
.\.venv\Scripts\python scripts\process_casablanca_traffic.py
.\.venv\Scripts\python scripts\process_hcp_population.py
.\.venv\Scripts\python scripts\build_casablanca_boundary.py
.\.venv\Scripts\python scripts\build_casablanca_network.py
.\.venv\Scripts\python scripts\build_pickup_candidates.py
.\.venv\Scripts\python scripts\generate_all_scenarios.py
.\.venv\Scripts\python scripts\write_dataset_manifest.py
.\.venv\Scripts\python scripts\make_casablanca_figures.py
.\.venv\Scripts\python -m pytest
```

## Next stage (explicitly out of scope here)

Online EVRP algorithms, PPO/GNN policies, and the event-driven simulator are **not** part of Stage 1.

## Scientific reminders

- Synthetic requests ≠ observed orders.
- Zonal TTI ≠ edge digital twin.
- Fleet energy = hypothetical depot-only profile.
