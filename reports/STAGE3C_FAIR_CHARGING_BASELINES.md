# Stage 3C — Fair charging baselines

## Shared controller

Module: `src/race_casablanca/policies/charging_controller.py`

| Mode | Rule |
| --- | --- |
| `none` | No controller-initiated charge |
| `adaptive_headroom` (primary) | Idle, no pending pickups, \(B-B^{\mathrm{res}}<\theta\) with \(\theta=3\) kWh → `request_return_depot(..., charge=True)` |
| `always_on_return` | Idle empty vehicles charge until nearly full (explicit skip when full to avoid zero-duration loops) |

Episode `SimConfig.charge_on_return` stays **False** in primary runs. Policies never flip that flag as a side effect of one vehicle decision.

Wired identically into: greedy, rolling horizon, RACE A/B/C/D, fixed-weight reference.

## Auxiliaries (peak_stress_seed2, SOC 35%)

| Mode | Greedy served | RACE-D served | Charges |
| --- | ---: | ---: | ---: |
| none | 18 | 21 | 0 |
| adaptive | 29 | 30 | 3 |
| always_on_return | 33 | 32 | 8 |

Charging intensity dominates service under low SOC. Primary scientific comparisons use **adaptive** for all methods.
