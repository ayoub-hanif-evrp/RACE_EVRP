# Stage 3B — RACE mathematical formulation

**Method name:** Risk-Aware Commitment and Energy Management for Online Electric Pickup Routing (non-learning prototype).

**Benchmark:** frozen `casablanca_release_v1`. No future request arrivals and no hidden energy realizations \(\xi\) are available to the decision maker.

## 1. Decision setting

At decision epochs (request release / vehicle free / bounded reoptimization triggers), the fleet observes the public available request set \(\mathcal{A}(\tau)\) and, under full information, the current vehicle planning states after locked-leg projection (Stage 3A semantics).

For vehicle \(v\), let \(\Pi_v^{\mathrm{lock}}\) be the immutable active stop and \(\Pi_v^{\mathrm{edit}}\) the editable pickup suffix. Planning uses conservative energy \(E^{\mathrm{cons}}(d)=c\cdot d\cdot(1+\delta)\).

## 2. Feasible commitment set (hard constraints)

A candidate insertion of request \(i\) into vehicle \(v\) at position \(p\) is **safe** iff the resulting editable plan \(\Pi\) satisfies, under conservative energy from the post-lock projected state:

1. Payload capacity at every pickup.
2. Time-window and shift-end service completion.
3. En-route battery never goes negative under \(E^{\mathrm{cons}}\).
4. After every pickup (and at plan end), a depot return remains feasible with battery \(\ge B^{\mathrm{res}}\).

Denote the safe insertion set by \(\mathcal{F}_v(i)\). RACE **never** accepts \(i\) on \(v\) outside \(\mathcal{F}_v(i)\). The same gate is used by greedy and rolling-horizon baselines.

## 3. Residual flexibility

For a feasible plan \(\Pi\), define:

- **Energy flexibility** \(\Phi_E(\Pi)=\max\{0,\,B^{\mathrm{final}}(\Pi)-B^{\mathrm{res}}\}\), where \(B^{\mathrm{final}}\) is the conservative battery after the plan including the required depot return.
- **Temporal flexibility** \(\Phi_T(\Pi)=\min_{i\in\Pi}(\ell_i-t_i^{\mathrm{svc\_end}})\), the minimum deadline slack (0 if \(\Pi\) empty).

These are computed from information available at \(\tau\); they are not forecasts of future demand.

## 4. State-dependent opportunity cost

Let \(\Pi_v\) be \(v\)'s current editable plan and \(\Pi_v\oplus i\) a feasible insertion. Incremental travel time \(\Delta T_v(i)\) is the conservative simulated travel of \(\Pi_v\oplus i\) (implementation uses total plan travel as the ranking travel term, consistent with greedy).

Define scarcity (shadow) prices from **pre-insertion** flexibility:

\[
\mu_E(v)=\frac{\alpha_E}{\varepsilon+\Phi_E(\Pi_v)/E^{\mathrm{typ}}},\qquad
\mu_T(v)=\beta_T\cdot\frac{T^{\mathrm{typ}}}{\varepsilon\,T^{\mathrm{typ}}+\Phi_T(\Pi_v)}.
\]

**Commitment score** (minimize):

\[
J_v(i)=\Delta T_v(i)+\mu_E(v)\cdot\max\{0,\Phi_E(\Pi_v)-\Phi_E(\Pi_v\oplus i)\}
+\mu_T(v)\cdot\max\{0,\Phi_T(\Pi_v)-\Phi_T(\Pi_v\oplus i)\}.
\]

Hard safety is binary; opportunity cost is soft and **state-dependent**: as residual energy/time flexibility shrinks, consuming more of it becomes more expensive. This is not a fixed weighted sum with constant coefficients on \(\Phi\).

Default prototype parameters (documented, not tuned on test): \(\alpha_E=240\,\mathrm{s}\), \(\beta_T=0.5\), \(E^{\mathrm{typ}}=2\,\mathrm{kWh}\), \(T^{\mathrm{typ}}=900\,\mathrm{s}\), \(\varepsilon=0.25\).

## 5. Assignment, reassignment, charging

**Primary rule (full information):** for each available request in earliest-deadline order, assign to \(\arg\min_{v:i\in\mathcal{F}_v(i)} J_v(i)\).

**Reassignment (optional):** if a vehicle’s \(\Phi_E\) falls below \(E^{\mathrm{typ}}\), attempt at most one pass moving a non-locked commitment to a vehicle with higher \(\Phi_E\) when destination insertion remains feasible under the same hard gate (`try_reassign`).

**Charging:** idle vehicles with battery headroom below a threshold may request depot charge. Charging is operational recovery, not a relaxation of the safety gate.

**Restricted information:** the same score is applied to self-insertions only; no privileged peer state.

## 6. Ablation

`use_opportunity_cost=False` sets \(J_v(i)=\Delta T_v(i)\) over \(\mathcal{F}_v(i)\), i.e. robust energy-feasible greedy. Any benefit of RACE over this ablation is attributable to the flexibility pricing (and optional reassignment), not to a different feasibility model.

## 7. Distinction from baselines

| Method | Hard gate | Soft ranking |
| --- | --- | --- |
| Robust greedy | conservative EV feasibility | min travel |
| Rolling horizon / LNS | same | min fleet travel under time budget; full reoptimize |
| Static weighted heuristic | same or weaker | fixed weights on energy/slack |
| **RACE (this stage)** | **same** | **state-dependent shadow prices on residual \(\Phi_E,\Phi_T\)** |

RACE does **not** claim novelty merely for \((1+\delta)\) robust energy checks. The candidate principle is **online pricing of residual commitment flexibility** under that gate, without requiring a demand forecast or a full fleet reoptimize each time.

## 8. Complexity and failure modes

Per decision with \(n\) available requests and \(m\) vehicles, primary scoring is \(O(n m P)\) insertion simulations (\(P\) insertion positions). Reassignment adds a bounded extra pass. Failure modes:

- Opportunity prices can over-protect energy and reduce service under high demand.
- Without forecasts, \(\Phi\) only proxies future option value; myopic ranking can still err.
- Gains may vanish when energy is abundant (prices near zero relative to travel) or when RH already finds near-optimal travel.

## 9. Information assumptions

Full-info RACE sees all vehicle visible states and available tasks. It never reads `en_route_energy_kwh` realized disturbances or unreleased requests. Restricted RACE sees only self + announcements (+ optional stale peer messages if used elsewhere; Stage 3B primary comparisons use full-info RACE vs full-info baselines, plus a restricted no-comm reference).
