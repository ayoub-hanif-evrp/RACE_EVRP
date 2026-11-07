# Stage 3C — Objective and insertion audit

## Corrections implemented

| Field / API | Meaning |
| --- | --- |
| `total_travel_s` | Conservative simulated travel of a full plan |
| `marginal_travel_s` | \(T(\Pi\oplus i)-T(\Pi)\) |
| `marginal_energy_kwh` | Conservative energy increase vs baseline plan |
| `energy_flex_kwh` / `min_deadline_slack_s` | Residual flexibility after plan + depot return |
| `insert_position` | Index in editable pickup suffix |

`evaluate_insertion()` enumerates **all** feasible positions. Greedy ranks by `marginal_travel_s`. RACE minimizes \(J(v,p)\) over vehicles **and** positions, then commits with `force_position`.

Legacy `added_travel_s` on insertions now equals **marginal** travel (not total).

## Deterministic tests

`tests/test_stage3c_objective.py`:

1. Geometry where min-total ≠ min-marginal; greedy selects the marginal winner.
2. RACE commits the chosen insertion index via `force_position`.
3. Shared charging controller does not flip `sim.config.charge_on_return`.

## Effect on Stage 3B numbers (honest)

Marginal-cost greedy changes peak-stress full-SOC service from the Stage 3B figure of **38/40** to **37/40** under adaptive charging (RH reaches **38/40** with lower energy). Low-SOC comparisons must use the Stage 3C equalized-charge runs, not Stage 3B’s charge-confounded table.
