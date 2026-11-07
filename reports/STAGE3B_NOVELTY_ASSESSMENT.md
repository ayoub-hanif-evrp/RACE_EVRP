# Stage 3B — Novelty assessment

## Acceptance decision: **PARTIAL — Technically correct, but scientific value remains uncertain.**

RACE is implemented with the same conservative feasibility gate as the baselines, passes targeted tests, and runs reproducibly on frozen Casablanca training scenarios. It does **not** yet demonstrate a TRC-grade advantage that is cleanly attributable to a new optimization principle once charging and strong RH baselines are controlled.

## What already exists (verified themes)

Relevant prior lines of work (not an exhaustive survey):

- **Dynamic / online EVRP with energy risk and charging**, including anticipative and safe-RL approaches for stochastic requests and consumption (e.g. dynamic stochastic EVRP with safe RL; Chalmers technical report / related publications on DS-EVRP).
- **Robust or conservative energy-feasible routing** via bounded consumption and reserve constraints — standard in EVRP practice; our \((1+\delta)\) gate is in this family, not a novelty claim.
- **Rolling-horizon / LNS reoptimization** for dynamic VRP — our centralized RH baseline embodies this; it already improves energy at equal service under full SOC.
- **Opportunity-cost / anticipatory insertion** in dynamic VRP (value of residual capacity; sampling or consensus methods) — conceptually closest soft-ranking idea; typically uses demand forecasts or sample scenarios.
- **Incentive / flexibility pricing** in EV routing (customer time flexibility, bi-level incentive models) — different object (customer delay markets), not fleet residual energy flexibility shadow prices.

## What RACE proposes

A transparent **state-dependent shadow price** on residual energy and deadline flexibility for online pickup **commitment ranking**, under a shared conservative safety gate, **without** sampling future requests.

That is a coherent design principle. It is also close to “opportunity-cost insertion with resource-scarcity weights.” Fixed weighted sums of slack and energy margin would be weaker; our prices \(\mu_E(v),\mu_T(v)\) respond to current \(\Phi\), which is the intended distinction from a static weighted heuristic.

## What the experiments support

| Claim | Support |
| --- | --- |
| Conservative gate preserves reserves in tested runs | Yes (0 violations) |
| Battery scarcity binds service | Yes (stress SOC cases) |
| Depot charging recovers service under low SOC | Yes; greedy+charge matches RACE 30/40 |
| Flexibility shadow prices beat robust greedy+charge | Not established |
| Flexibility prices beat RH on service or energy | No at full SOC; mixed under low SOC where RH lacked auto-charge |
| Ablation shows consistent mechanism benefit | Weak / inconsistent (+1, +1, −2, +3 served) |

## Honest novelty stance for TRC

**Not sufficient yet** as a Part C contribution if framed only as “we weight energy flexibility.” To proceed toward a learning extension or a journal claim, one of the following must be earned next:

1. A **theoretical property** (e.g. competitive ratio / safety certificate beyond the shared robust gate) unique to the pricing rule; or  
2. **Consistent paired gains** over charge-enabled robust greedy **and** documented-budget RH on held-out scenarios; or  
3. A sharper mechanism (forecast-light anticipatory value with proven structure) that the current heuristic only sketches.

## Recommendation

Treat Stage 3B RACE as a **working non-learning prototype and diagnostic**: it shows where value appears (energy scarcity + charging + mild reassignment) and where the proposed shadow-price term is not yet decisive. Do **not** train PPO/GNN/MARL until the decision being learned is specified more tightly than “imitate this heuristic.”
