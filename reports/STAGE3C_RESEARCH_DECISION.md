# Stage 3C — Research decision

## Decision: **FAIL**

The corrected non-learning RACE inverse-slack flexibility heuristic does **not** justify further development as the methodological core of a Transportation Research Part C paper. Do **not** train a neural imitation of this heuristic.

## Inverse-slack price analysis (Task 4)

Let \(\mu_E=\alpha_E/(\varepsilon+\Phi_E/E^{\mathrm{typ}})\) and \(\mu_T=\beta_T\,T^{\mathrm{typ}}/(\varepsilon T^{\mathrm{typ}}+\Phi_T)\).

| Property | Assessment |
| --- | --- |
| Units | \(\mu_E\) maps kWh loss → seconds; \(\mu_T\) mixes slack seconds into the travel objective — coherent but arbitrary scale |
| Monotonicity | \(\mu\) rises as residual flexibility falls (intended) |
| Empty plan | \(\Phi_T=0\) maximizes \(\mu_T\); empty vehicles can be over-penalized for accepting the first task |
| After charging | \(\Phi_E\) jumps → prices collapse; charging already carries most low-SOC value |
| Unused capacity | Prices residual energy even when remaining shift demand is low — over-protects |
| Dual / ADP status | **Heuristic scarcity weights, not optimization duals or calibrated future values** |

Traces show pricing often changes \((v,p)\) yet frequently **reduces** service under full SOC and is unstable under reassignment coupling.

**Replacement not shipped in 3C:** a training-calibrated post-decision service-capacity value \(V(\Phi_E,\Phi_T,\tau)\) with a conventional one-step rollout baseline would be the principled next *formulation*, but implementing it here would restart method design after the equalized experiments already reject the current claim. That work belongs to a reformulated stage, not a neural bolt-on.

## Literature distinction

Established: DS-EVRP / safe RL with predictive charging; Ulmer-style ADP/rollout for dynamic VRP; opportunity-cost insertion with sampled future demand; robust EV energy gates. Our inverse-slack online commitment score is an incremental scarcity heuristic inside that landscape, not a new principle once charging and marginal insertion are equalized.

## Why not PASS / PARTIAL

- **PASS** requires reproducible advantage over charge-enabled greedy **and** strong RH, or a distinct theory property. Neither holds.
- **PARTIAL** would fit “occasional gains under δ>0 (e.g. B 29 vs 25 on peak2)” — real but too brittle and not the full RACE (D) story. Ranking the *current packaged method* as FAIL is clearer scientifically.

## Reformulation recommendation (not neural)

Redirect the research question to:

> How should an online EV pickup fleet value **residual energy-feasible service capacity** after a commitment, jointly with **explicit charge timing**, under the same conservative safety certificate?

Concrete next method (non-learning first): train-only calibration of a low-dimensional post-decision value or one-step rollout on remaining shift demand proxies; compare to charge-enabled marginal greedy and documented-budget RH; hold charging controller fixed. Only then consider learning that value function if the non-learning anticipatory rule shows a clean gap.
