# Stage 2 — Research novelty assessment

Target journal: *Transportation Research Part C: Emerging Technologies*.  
Status: **hypothesis only** — Stage 2 does not claim a proven methodological contribution.

## Candidate research question

Online electric parcel pickup with incomplete fleet-state information:

> When EVs receive dynamic pickups but have incomplete knowledge of peers’ commitments and energy states, which information is worth exchanging, and how can vehicles make reliable task-acceptance decisions without sacrificing fleet efficiency?

Proposed long-term contribution (to be tested, not asserted):

**Energy-feasible task commitment + decision-relevant information exchange** — linking the expected routing value of a message to the feasibility / opportunity cost of changing a commitment.

## What existing work already covers

| Paper | What it addresses | Gap relative to RACE hypothesis |
| --- | --- | --- |
| Chen et al., TRC 2026, [10.1016/j.trc.2025.105387](https://doi.org/10.1016/j.trc.2025.105387) | Dynamic VRP/scheduling with stochastic request times and time-dependent stochastic travel; end-to-end RL (DSTMP-RL) with attention / multi-pointer decoding; Vienna road experiments | Conventional (non-EV) DVRP focus; centralized learning of routes/departures; **no EV energy commitments, no communication value of SOC/task ownership** |
| Shahbazian et al., COR 2025, [10.1016/j.cor.2025.107217](https://doi.org/10.1016/j.cor.2025.107217) | Dynamic multi-depot EVRPTW; hybrid MARL (DDQN) + VNS; knowledge-guided action masking | Multi-depot EV routing with learning, but **not** about which commitment/energy messages are decision-relevant under partial information |
| Ren et al., TRE 2026, [10.1016/j.tre.2026.104900](https://doi.org/10.1016/j.tre.2026.104900) | Dynamic multi-agent pickup-and-delivery under **communication uncertainty** (warehouse robots); radio-map delays; token-passing replanning | Closest on communication delays, but **warehouse MAPD**, not urban EV energy/depot-charging pickup logistics |
| Han et al., TRE 2025, [10.1016/j.tre.2025.104211](https://doi.org/10.1016/j.tre.2025.104211) | Robust EVRP with uncertain travel time **and** energy; adaptive robust optimization; recharging decisions | Strong on energy/travel uncertainty, but **offline/robust optimization**, not online partial-information messaging about commitments |
| Liu et al., Applied Energy 2026, [10.1016/j.apenergy.2026.127612](https://doi.org/10.1016/j.apenergy.2026.127612) | Transformer-enhanced MARL (TE-MARL/PPO, CTDE) for electric fleets under time-varying traffic and grid-coupled charging | Architecture-heavy EV fleet RL; **does not formulate decision value of communicating energy-feasible task commitments** |

## What is *not* automatically novel

Combining MARL + transformers/attention + risk-aware energy + event-triggered communication is **not** a contribution by itself. Each piece appears in the table above.

## Candidate gap (precise)

A methodological opening remains if we can show:

1. Online **acceptance/reassignment** of pickups is constrained by **conservative energy-to-depot commitments**, not only by travel time; and  
2. Under **restricted fleet information**, the **value of a message** can be tied to whether it changes a feasible commitment set (feasibility / opportunity cost), not merely to learning when to broadcast; and  
3. This joint energy–information mechanism improves on strong **centralized rolling-horizon** and **restricted-information non-learning** baselines on a documented urban EV pickup setting.

Stage-2 evidence (see `STAGE2_BASELINE_RESULTS.md`):

- (1) is **alive** under plausible low-SOC / energy-uncertainty settings (peak stress serve rate collapses; reserve violations appear).  
- (2)–(3) are **not yet supported** on serve rate: restricted-info baselines matched full-info greedy on the tested instances. A communication contribution needs finer coordination metrics or harder information regimes.

## Unresolved novelty risks

- If energy almost never binds under realistic SOC, the “energy-feasible commitment” half collapses to ordinary online VRP.  
- If limited information does not degrade service vs full-info baselines, communication value is weak.  
- Ren (2026) already treats delayed coordination; differentiation must be **EV energy commitments on road networks**, not token-passing alone.  
- Han (2025) already treats energy uncertainty robustly; differentiation must be **online partial-information commitments**, not another robust EVRP.  
- Reviewers may view architecture choices (GNN/transformer/MARL) as incremental unless the **information-value / commitment** mechanism is formalized and ablated.

## Stage-2 stance

Do **not** implement the novel method yet. Use simulator evidence to keep, refine, or abandon the hypothesis before selecting a neural architecture.
