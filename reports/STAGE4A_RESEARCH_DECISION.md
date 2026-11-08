# Stage 4A — Research decision

## Decision: **FAIL**

The Stage 4A post-decision service-capacity pilot is technically runnable and information-safe, but it does **not** demonstrate a distinct defensible methodological contribution or a meaningful reproducible advantage over strong charge-aware baselines and a conventional one-step rollout.

Do **not** proceed to PPO/GNN/MARL to “learn” this lookahead.

Stage 3C FAIL for inverse-slack RACE remains in force.

## Why not PASS / PARTIAL

- **PASS:** Requires advantage vs charge-enabled greedy **and** strong RH/rollout, or a new theoretical property. Pilot shows ≈ adaptive greedy; loses to always-on at low-SOC peak; no clear edge vs one-step rollout.
- **PARTIAL:** Would require a promising, stable gap attributable to the joint charge–commitment \(\widehat{Q}\). Observed gaps are absent or dominated by charging-rule choice.

## Specific reformulation recommendation

Stop inventing new acceptance heuristics that re-package rollout.

If the PhD contribution continues on Casablanca EV pickups, the sharper open problem is:

> **Optimal (or certifiably near-optimal) timing of depot charging under online pickup commitments with conservative energy certificates** — including when *not* to charge — with competitive analysis or tight bounds versus always-on and threshold policies.

That problem is grounded in Stage 3C/4A evidence (charging dominates), is not solved by inverse-slack prices or shallow MC rollout, and must be positioned carefully against Basso et al. and related EV anticipatory work before any learning stage.
