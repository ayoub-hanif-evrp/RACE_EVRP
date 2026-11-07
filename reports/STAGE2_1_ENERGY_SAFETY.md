# Stage 2.1 — Energy safety

## Stage-2 inconsistency (resolved)

`stress_low_soc` previously reported ~29.15 kWh consumed with 5 reserve violations while only 24 kWh sat above fleet reserve at 35% SOC and zero charging. That contradicted a correct conservative bound.

**Root causes:** auto depot / pickup departures without a pre-dispatch conservative+reserve gate; planning from stale vehicle state while busy; counting violations after unsafe travel.

## Corrected mechanism

1. Planning uses conservative energy \(E^{\mathrm{cons}}=(1+\delta)E^{\mathrm{nom}}\).
2. Realized energy uses CRN \(xi\) from `(seed, vehicle_id, leg_seq)`, or `adversarial_worst` (\(xi=+\delta\)).
3. Every departure passes `check_leg_dispatch` (leg + depot-with-reserve). Failure ⇒ planned rejection and/or `EMERGENCY_STRANDED` — **no travel**.
4. Under \(xi \le \delta\), realized energy ≤ conservative planning energy for each gated leg.

## Adversarial verification

Synthetic + Casablanca `peak_stress` with `realization_mode=adversarial_worst`, SOC=0.35, δ=0.2:

- `battery_reserve_violations = 0`
- `battery_exhaustion = 0`
- Serve rate drops (14/40) via **planned rejections / fewer commits**, not post-hoc reserve breaches.

Traces: `data/casablanca/online_results/stage2_1_energy_traces.json`.

## OAT energy results (greedy, seed=1)

| Experiment | Served | Energy (kWh) | Reserve viol. | Plan energy rej. |
| --- | ---: | ---: | ---: | ---: |
| baseline SOC=1.0, δ=0 | 10/12 | 24.95 | 0 | 0 |
| baseline SOC=0.35, δ=0 | 9/12 | 21.34 | 0 | 0 |
| baseline SOC=0.35, δ=0.2 | 8/12 | 21.26 | 0 | 0 |
| stress SOC=1.0, δ=0 | 38/40 | 55.56 | 0 | 0 |
| stress SOC=0.35, δ=0 | 20/40 | 23.19 | 0 | 0 |
| stress SOC=0.35, δ=0.2 | 20/40 | 23.09 | 0 | 0 |
| stress SOC=0.35, adversarial +δ | 14/40 | 22.37 | **0** | 0 |

**Conclusion:** Energy is decision-active under reduced SOC. The corrected conservative commitment rule maintains the promised reserve under the declared bound. Stage-2’s five violations were simulator bugs, not evidence that uncertainty “defeated” a correct gate.

## Common random numbers

`EnergyModel.realization_mode=crn` hashes `(scenario_seed, vehicle_id, leg_seq)` so exogenous disturbances are independent of policy branching order for the same leg index sequence. Documented limitation: policies that take different numbers of legs still diverge after that point.
