# Non-linear charging (linear model removed)

Depot charging uses a **piecewise-linear SOC–time curve** (CC–CV style):

- Early SOC charges faster.
- Near-full SOC tapers (slower).
- Duration = `T(soc_to) - T(soc_from)` — **not** `ΔkWh / constant kW`.

Config: `configs/fleet_default.yaml` → `charging_curve`  
Code: `src/race_casablanca/sim/energy.py` (`charge_duration_s` / `charge_duration_kwh`)

All previous experiment outputs under `data/casablanca/online_results/` that used linear charging were deleted and must be re-run.
