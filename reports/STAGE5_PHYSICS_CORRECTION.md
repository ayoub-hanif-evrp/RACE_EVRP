# Stage 5 — Physics correction (partial-charge planning)

## Bug

`projected_state_after_lock` and `simulate_plan_conservative` treated every `depot_charge` as a full refill to `B_max`, while the simulator honored `Stop.target_kwh`. That inflated projected battery and charging duration for 50%/70% targets.

## Fix

Helper `apply_depot_charge` in `src/race_casablanca/sim/feasibility_check.py`:

- `target = clip(stop.target_kwh or B_max, battery, B_max)`
- duration from `max(0, target - battery)` at charge power
- both projection sites call this helper

`missed` requests are non-assignable in plan simulation.

## Shift-end interpretation (locked)

- Pickup service must finish by `min(tw_end, shift_end)`.
- Final depot return / charge completion **may** finish after `shift_end`.

## Tests

`tests/test_stage5_partial_charge_planning.py` — targets 50/70/100; energy vs deadline trade-offs; locked partial charge projection; planned vs simulated delivered energy under δ=0.

Stage 4B Casablanca gap numbers predate this fix and should be re-checked under Stage 5 runners where planning uses partial targets inside RH.
