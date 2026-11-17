# Casablanca C / R / RC dataset (realistic OSM buildings)

## Classes (no numbered series)

| Class | Meaning |
|---|---|
| **C** | Clustered customers (few communes) |
| **R** | Dispersed customers |
| **RC** | Mixed clustered + dispersed |

Sizes: **15 / 30 / 45** customers.

## Realism rules

1. Customer locations come from **`pickup_candidates_realistic.csv`**.
2. Frame includes **typed OSM buildings** (`house`, `apartments`, `commercial`, `office`, …), **shops**, **offices**, and service **amenities**.
3. **Excluded:** generic `building=yes`, parking, fuel, benches, etc.
4. **`lat` / `lon`** = OSM feature point or building-polygon **centroid** (the place).
5. **`snap_node`** = nearest drive-graph node for **routing access only** — not a random customer projection.

## Layout

```text
data/casablanca/evaluation_v1/solomon_style/
  C/n15/...
  C/n30/...
  C/n45/...
  R/n15/...
  RC/n45/...
  ensemble_index.json
```

## Commands

```bash
python scripts/build_realistic_pickup_frame.py
python scripts/generate_solomon_style_ensemble.py --replace --per-class-size 5
```

`locked_final` remains untouched (legacy Prompt-3 holdout).
