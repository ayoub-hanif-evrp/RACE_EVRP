# RACE method decision — first communication milestone

**Date context:** post Stage 6 (`10a88de` lineage).  
**Question:** Does energy-certified task-specific bidding + selective messaging create real operational value vs the same rule with no peer communication?

## Binding assessment

**YES — provisional go for Phase 5 scale-up. NO MARL yet.**

Evidence from the non-learning pilot:

- Same assignment rule; messaging ablated.
- Selective and full both improve mean SOC35 on-time by ~**+2.7 pp** vs none (n=4).
- Selective matches full service with **72 vs 336** mean policy messages and equal CF decision changes (**11.25**).
- Random messaging does not match that effect.

This directly addresses the Stage 3A failure mode (messages without useful dispatch logic).

## What we will **not** claim yet

- Statistical significance / generalization across fleet sizes and delays.
- Superiority to all centralized rolling-horizon methods on all instances.
- Novelty of auctions or event triggers alone.
- Readiness for TR Part C without Phase 5–7 evidence.

## Next allowed work

1. Phase 5: larger paired matrix (fleet 3/5/10, workloads, delays, packet loss) on frozen Casablanca geography; regenerate spatial sensitivity with fixed `pop_w`/`com_w`.
2. Write `RACE_SCALABILITY_AND_GENERALIZATION.md` and `RACE_NOVELTY_POSITIONING.md` from those results.
3. Phase 6 MARL **only if** Phase 5 reproduces a clear service–communication Pareto benefit.

## Retained assets

- Stage 6 RACE-RH negative control and charging baselines.
- `casablanca_release_v1` + `evaluation_v1` / `locked_final` (locked still untuned).
