# Casablanca Stage-1 research method (`casablanca_release_v1`)

## Problem setting

Reproducible Casablanca benchmark for **online electric parcel pickup with depot-only charging**. No routing/learning algorithms (PPO, GNN, event-driven EVRP simulator) are included in Stage 1.

## Spatial definition

Workbook communes \(\mathcal{Z}\) (22) are either `verified_admin` OSM polygons or documented `approximate_study_zone` OD-hull study areas. Study area \(\mathcal{A}\) is their union. Al Idrissia and Sidi Maarouf use OD hulls after rejecting incorrect Nominatim admin matches.

## Road graph

Directed drive graph from frozen Geofabrik PBF clipped to \(\mathcal{A}\), reduced to the largest strongly connected component (~18% of post-WCC nodes excluded).

## Congestion model (matches source code)

Workbook TTI factors \(f(z,d,h)\) multiply a **60 km/h TTI-reference free-flow baseline**:

\[
t(e,\tau)=\frac{3.6\,\ell(e)}{60}\cdot f\big(z(e),d,h(\tau)\big).
\]

This 60 km/h reference is an empirical modeling approximation aligned with the workbook free-flow identity \(d/(t/\mathrm{TTI})\approx 60\). It is **not** a claim that every street has observed free-flow speed 60 km/h. OSM class speeds are retained as provenance only and are not the congestion baseline.

Citywide hourly factors are the fallback when zone×day factors are unavailable. FIFO waiting is applied at hour boundaries when beneficial.

## Synthetic demand

See `CASABLANCA_DEMAND_GENERATION.md`. Weights come exclusively from `demand_zone_weights.csv`.

## Feasibility certificates

Graph constructive witnesses with independent validation: coverage, fleet IDs, correct `snap_node`, shift start, energy/payload/windows, depot return, recorded `path_edge_keys`. Offline full-information schedules — not online policy performance.

## Observed vs modeled

| Quantity | Status |
| --- | --- |
| Workbook TTI by zone/day/hour | Observed (published Waze-derived) |
| OSM geometry / PBF snapshot | Observed archive |
| HCP RGPH-2024 population (matched verified zones) | Observed census join |
| Request locations / times / packages | Synthetic |
| Edge-level speeds under congestion | Modeled approximation |
