# Stage 4B — Research reformulation

## What Stage 4B established

Online Casablanca EV pickup under **hard deadlines** and **depot-only discrete target-SOC charging** is a coherent research object distinct from:

- Stage 3C inverse-slack commitment scoring (**FAIL**, preserved),
- Stage 4A post-decision MC synthetic futures (**FAIL**, preserved).

Tiny exact instances show that **when** and **to which target** the vehicle charges changes the achievable on-time set. Equalized online diagnostics show the same on train peak/tight scenarios: always-full vs charge-to-0.7 vs adaptive is a real peak–tight trade-off.

## Literature positioning (brief)

Classical EVRP / EVRPTW and depot-charging literature optimize routes with continuous or segmented charge quantities, often offline or with soft windows. Online dynamic pickup with **locked commitments**, **conservative energy**, and a **small discrete charge alphabet** tied to on-time rate among releases is closer to dynamic DVRP + opportunity charging than to electricity-price smart charging. Stage 4B does not claim a new continuous charging market model.

## One candidate structure (if pursuing a method next)

**Discrete target-SOC charging–commitment DP / bounded enumeration** over the same action alphabet used online:

- State: (time bucket, SOC bucket / last target, locked vs editable commitments, residual feasible set sketch).
- Actions: claim/skip pickup; charge-to-{0.5, 0.7, 1.0}; wait/return.
- Objective: lexicographic on-time, then distance/energy.

Not inverse-slack. Not Stage 4A MC rollout revival. Not neural nets at this stage.

## What not to do

No Casablanca rebuild; no PPO/GNN/MARL; no communication revival; do not rehabilitate 3C/4A heuristics as the novelty claim.
