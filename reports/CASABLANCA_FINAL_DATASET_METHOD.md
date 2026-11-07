# Casablanca final dataset method (`casablanca_release_v1`)

## Scope

Synthetic online electric parcel-pickup benchmark for Casablanca. Not observed parcel orders. Not an edge-calibrated traffic twin.

## Pipeline order

1. Verify pinned study boundary SHA-256  
2. Rebuild directed drive graph from frozen Geofabrik PBF + boundary  
3. Extract/snap/assign pickup candidates  
4. Build `demand_zone_weights.csv` (HCP measured only on verified_admin matches)  
5. Generate scenarios atomically (staging → replace)  
6. Verify release

## Demand

- Generator `0.3.1`; regimes: baseline **12**, peak_stress **40**, tight_windows **30** requests  
- Spatial mix 60% population / 40% commercial buildings on eligible zones  
- Population term uses HCP RGPH-2024 only when zone is `verified_admin` and HCP-matched  
- Approximate zones: commercial-only; no silent citywide candidate fallback  

## Geography

- 15 `verified_admin`, 7 `approximate_study_zone` (incl. repaired Al Idrissia & Sidi Maarouf OD hulls)  
- Candidates assigned by point-in-polygon with verified_admin priority on overlaps  
- Network retains largest SCC; ~18.3% of post-WCC nodes excluded  

## Travel times

Operational congestion:

\[
t(e,\tau)=\frac{3.6\,\ell(e)}{60}\cdot \mathrm{TTI}(z,d,h(\tau))
\]

The **60 km/h** factor is an empirical TTI reference consistent with the workbook free-flow identity, **not** a claim that every Casablanca street has observed free-flow speed 60 km/h. OSM class speeds remain provenance attributes only.

## Feasibility certificates

- Shift start = regime `start_hour` (baseline 08:00)  
- Customer service must finish by shift end; depot return may finish after  
- Pickup credited only at request `snap_node`  
- Parallel edges recorded via `path_edge_keys`  
- Uncertified builds never retain `reference_schedule.csv`  

## Pickup candidates

Raw OSM features retained (`building`, `amenity`, `shop`, `office`). Category mix is dominated by generic `building=*` tags (~87%). These are **mapped places**, not verified parcel customers. Treat as a transparent candidate-location model, not empirical demand origins.

## Train / validation / test

Seeds from `configs/demand_default.yaml` only (legacy seed 42 excluded from release).
