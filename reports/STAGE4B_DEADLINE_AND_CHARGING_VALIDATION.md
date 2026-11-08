# Stage 4B — Deadline and charging validation

## Hard deadlines

- Arrival gate in `OnlineSimulator._on_arrival`: if `max(now, tw_start) + service_s > tw_end`, request → `RequestStatus.MISSED` with trace reason `deadline_unreachable_on_arrival`.
- No `IN_SERVICE` / `COMPLETED` on late arrival. `COMPLETED` sets `on_time=True`.
- Primary metric alias: `on_time_rate = on_time_rate_all` (on-time / released).
- Feasibility planner already rejected infeasible insertions; simulation now matches for adversarial / injected late arrivals.

## Discrete target-SOC charging

- `Stop.target_kwh` on `depot_charge`.
- `request_return_depot(..., charge=, target_soc=)` clips target to `[battery, B_max]`.
- Metrics: `energy_delivered_kwh`, `charge_duration_s` on vehicles and `EpisodeMetrics`.
- `ChargingController` modes: `none | always_on_return | adaptive_headroom | charge_to_target` with `target_soc` (alphabet `{0.50, 0.70, 1.00}`).

## Tests

`tests/test_stage4b_deadlines_and_charging.py`

- Late arrival after window shrink → `MISSED`, not `COMPLETED`.
- Injected impossible plan → `MISSED`.
- Partial vs full charge: less energy and shorter duration for target 0.7 vs 1.0.
- Controller `charge_to_target` queues depot charge with target.
- Greedy episode: every `COMPLETED` has `on_time=True`.
