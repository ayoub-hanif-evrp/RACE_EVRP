# Solomon-style Casablanca dataset organization

## Why

Legacy regimes used **12 / 30 / 40** customers. Reviewers can fairly ask “why 12?”.  
This family reorganizes synthetic Casablanca demand into **Solomon-inspired classes** with sizes **15 / 30 / 45**.

## Design

| Axis | Values | Meaning |
|---|---|---|
| Class pattern | **C / R / RC** | Clustered / dispersed / mixed communes |
| Series | **1 / 2** | Tight windows / wide windows |
| Size | **15 / 30 / 45** | Customers per instance |
| Named classes | **C1, C2, R1, R2, RC1, RC2** | pattern × series |

Fleet defaults: 15→3 EVs, 30→5, 45→6.

## Layout

```text
data/casablanca/evaluation_v1/solomon_style/
  C1/n15/C1_n15_seed..../
  C1/n30/...
  ...
  RC2/n45/...
  ensemble_index.json
```

Manifest: `data/casablanca/manifests/casablanca_solomon_style_v1.json`  
Config: `configs/demand_solomon_style.yaml`

## Honesty

- Real OSM Casablanca geography + synthetic orders  
- **Not** Euclidean Solomon coordinate files  
- **Does not replace** `locked_final` (legacy Prompt-3 holdout stays untouched)

## Generate / train

```bash
python scripts/generate_solomon_style_ensemble.py --per-class-size 5
python scripts/train_race_marl.py --mode casablanca --episode-source solomon_style ...
```
