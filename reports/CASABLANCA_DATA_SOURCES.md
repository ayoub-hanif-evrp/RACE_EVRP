# Casablanca Stage-1 data sources

## Primary sources used

| Source | Role | License / access | Status in this build |
| --- | --- | --- | --- |
| Rouky & Bousouf Mendeley workbook DOI `10.17632/8hj76bpzpv.1` | Zone×day×hour congestion (TTI), 22 communes, OD endpoints | CC BY 4.0 | Downloaded; SHA-256 verified |
| Geofabrik `morocco-260101.osm.pbf` | Archived Morocco OSM extract for provenance | ODbL | Downloaded; MD5 verified |
| OSMnx Overpass / Nominatim queries on the study boundary | Directed drive graph, admin polygons, pickup POIs | ODbL | Built successfully |
| HCP RGPH-2024 legal population Excel (`hcp.ma/file/242341/`) | Commune/arrondissement population covariates | HCP official publication | Downloaded; 16/22 zones matched |

## Optional / related sources (inspect only)

### SUMO Casablanca network (Zenodo 21539315)

- **Suitability:** Simulation network packaging, not measured traffic.
- **Reuse decision:** Inspect only. Never treated as observed congestion or demand.
- **Stage-1 use:** Not ingested into travel times or scenarios.

### MDPI Casablanca logistics paper (2025)

- **Suitability:** Related work on urban logistics framing.
- **Reuse decision:** Citation / literature context only.
- **Stage-1 use:** No order data extracted; synthetic demand remains labeled modeled.

### HELECAR-D (Rabat–Salé small EVs)

- **Suitability:** Optional energy plausibility reference for light electric vehicles in a nearby Moroccan setting.
- **Reuse decision:** Not a Casablanca delivery-van measurement.
- **Stage-1 use:** Delivery-van Wh/km stays a labeled hypothetical profile in `configs/fleet_default.yaml`.

## Claim boundary

Allowed claims are limited to published Waze-derived zonal/hourly congestion, OSM geometry/distances, synthetic geographically grounded pickups, and a hypothetical depot-only EV fleet. Edge-calibrated digital-twin traffic, observed Casablanca parcel orders, and Chinese/LaDe demand are out of scope.
