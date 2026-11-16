# FINAL ENERGY AND RUNTIME VALIDATION

## Field mapping (fixed)

| Reported quantity | Simulator field |
|-------------------|-----------------|
| Traction energy | `EpisodeMetrics.energy_consumed_kwh` |
| Charging energy | `energy_delivered_kwh` |
| Charge duration | `charge_duration_s` |
| Charge count | `n_charges` |
| Distance | `total_distance_m` |
| Decision mean/p50/p95 | `mean/p50/p95_decision_runtime_s` → ×1000 for ms |
| Decision count | `n_decisions` |
| Strandings | `n_strandings` |

Extractor: `src/race_casablanca/coordination/experiment_metrics.py`  
Do **not** use nonexistent `total_energy_kwh` or `mean_decision_ms`.

## Verification

- Unit test: moving EV ⇒ `energy_consumed_kwh > 0`  
- Primary matrix: min energy among OK rows ≈ 10.13 kWh; H@0 mean ≈ 34.4 kWh  
- Decision: min mean runtime ≫ 0; H@0 mean ≈ 116.5 ms  

## Architecture note

`wait_authority=decentralized_signal` does **not** probe cross-fleet energy travel for wait length.  
Energy feasibility is enforced at the **claim gate** via conservative insertion — separate from timing.
