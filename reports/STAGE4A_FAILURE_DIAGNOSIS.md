# Stage 4A — Failure diagnosis (Stage 3C)

Stage 3C FAIL for inverse-slack RACE is preserved. This note isolates *why* equalized experiments behaved as they did, using stored metrics and charging-controller semantics (commit `00aa2fc`).

## 1. Why always-on-return beats adaptive (peak_stress_seed2, SOC 35%)

| Charging | Greedy served | Charges | Driving energy kWh |
| --- | ---: | ---: | ---: |
| none | 18/40 | 0 | 23.03 |
| adaptive (θ=3 kWh headroom) | 29/40 | 3 | 43.54 |
| always_on_return | **33/40** | **8** | 42.71 |

**Mechanism:** Adaptive waits until \(B-B^{\mathrm{res}}<3\) before requesting charge. Under peak demand and 35% SOC, many requests become energy-infeasible *before* that threshold is hit, so the fleet “runs empty” of feasible capacity mid-shift. Always-on-return restores battery earlier and more often (8 vs 3 sessions), keeping more future insertions feasible.

**Counterfactual implication:** The missed gap 29→33 is largely **timing of energy recovery**, not residual-flexibility pricing. Full RACE-D under adaptive reaches 30/40; under always-on, 32/40 — still below always-on greedy.

## 2. Missed-request causes (aggregate evidence)

Stage 3C does not store per-request rejection reasons in the CSV, but simulator counters and policy behavior imply a mixture of:

- **Energy / reserve-binding** under low SOC (service collapses without charging; planned energy rejections rise when δ>0).
- **Deadline / shift** under tight_windows (full-SOC gaps persist even with full batteries).
- **Positioning / travel** secondary once energy is restored (always-on recovers many energy-blocked requests).

Changing charging from adaptive→always-on recovers **+4** requests for greedy on peak2 SOC35 — evidence that **charging time** was a binding enabler for those requests.

## 3. Would different charging make missed requests feasible?

Yes for a substantial subset under low SOC: always-on vs adaptive demonstrates physical feasibility once energy is replenished earlier. It does **not** recover all 40 (33/40 remains), so deadlines and fleet size still bind.

## 4. Does rolling horizon sacrifice service for travel?

Sometimes. Peak2 full SOC adaptive: RH **38/40** vs greedy **37/40** (RH better on service *and* energy). Peak2 SOC35: RH 30 vs greedy 29. Tight3 full SOC: RH **24** vs greedy **26** — here RH’s travel-minimizing LNS **loses service**. A **service-first** RH is therefore required as a credible Stage 4A baseline.

## 5. Reassignment churn without service gain

Peak2 SOC35 adaptive: variant C (reassign only) uses **20** reassignments for the same 29 served as A; D uses **11** reassignments for 30 served. Under δ=0.2, B (price only) reaches **29** while D falls to **27** with reassignment. Conclusion: scarcity-triggered reassignment often spends compute/churn without reliable service improvement — drop as a default mechanism.

## Diagnosis summary

| Factor | Role in Stage 3C FAIL |
| --- | --- |
| Inverse-slack prices | Change \((v,p)\) but inconsistently; fixed weights often match |
| Reassignment | High churn, unstable interaction with pricing |
| Adaptive charging threshold | Leaves recoverable service on the table vs earlier charging |
| Travel-first RH | Occasionally under-serves vs marginal greedy |

**Reformulation target:** jointly value **commitment vs charge-now** by estimated **future on-time service capacity**, not by leftover kWh/slack alone.
