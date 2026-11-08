# Stage 5 — Joint optimization model (RACE-RH)

## Online decision epoch

At time \(t\), observe only currently released requests and current vehicle states. Unreleased future demand is unavailable.

## Decision variables (per epoch)

- Editable pickup assignment and order per vehicle (locked active legs immutable).
- Depot visits with discrete charge targets \(\{0.50, 0.70, 1.00\}\) clipped to \([\mathrm{SOC},1]\).
- Noop (no charge) is always allowed.

## Constraints

- Conservative energy en-route and reserve after each pickup (return-to-depot check).
- Hard deadlines: service finish \(\le \min(\ell_i, \tau^{\mathrm{end}})\).
- Payload capacity.
- Atomic fleet plan commit; failed commit restores prior safe state.
- Final depot return / charge may complete after shift end.

## Lexicographic objective

1. Maximize number of on-time-feasible committed pickups in the planned schedule.
2. Minimize total planned travel time.
3. Minimize planned energy delivered (prefer less unnecessary charging).
4. Computation time is measured separately (not traded against service).

## Decomposition

- **Outer:** service-first rolling-horizon neighborhood on assignments/orders within a CPU budget.
- **Inner:** resource-constrained charging DP for a **fixed** pickup sequence (`optimize_charge_schedule`). Exact for continuous time + discrete targets under the declared insertion pattern (leading / between / trailing charges).

Not a global clairvoyant EVRP optimum.
