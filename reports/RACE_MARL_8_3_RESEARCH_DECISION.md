# RACE-MARL Stage 8.3 — Research Decision

## Decision: **PARTIAL**

### What passed

1. **Event-driven parity:** MARL now returns on `service_end` / idle / charge_end with deferred autoleg. Native `RaceCooperativePolicy` executed on that schedule recovers ~0.82 OT (vs ~0.49 learned pre-fix).
2. **Action safety:** Charge masking + commitment-preserving depot returns; adversarial tests green.
3. **Teacher diagnosis:** Factorized adapter ≠ native; native-bridge intent after soft-assign/charge fixes is a valid factorized teacher (mean ~0.60; peak ~0.85).
4. **Imitation recovery:** Weighted BC+DAgger reaches the factorized ceiling (~0.63 mean), above Stage 8.2 learned ~0.49.
5. **Non-learning communication:** Selective still matches full OT at much lower bytes; delay/owner counterfactuals remain credible.

### What remains unresolved

1. Factorized + batched `env.step` still loses ~20pp vs sequential native (divergence traces: simultaneous duplicate `op=0` awards wrong owner vs native sequential/two-phase).
2. Learned A/C/D ~0.63 with **no service advantage** for F/E communication; F/E mean 0.564 (seed-2 forgetting).
3. Validation-subset selection (2 scenarios) can look stronger (0.775) than the six-scenario mean (0.63).
4. Intent bridge still misses ~16 feasible pickups/episode on average (adapter misses 0) — residual teacher mapping issue inside the factorized ceiling.

### What we will not claim

- MARL superiority over the rule-based cooperative protocol.
- A learned selective-communication service–bandwidth advantage.

### Recommended paper center of gravity

Lead with the **validated non-learning selective protocol** (safe bids, matched service, lower bandwidth, causal ownership effects). Treat MARL as infrastructure + negative/partial result: after correcting event parity, learned policies reach a factorized ceiling but do not match sequential cooperative competence or demonstrate learned communication value.

### Next step (not Stage 9 yet unless pivoting)

Either (a) manuscript pivoting to non-learning communication + MARL diagnostic appendix, or (b) a narrow follow-up that makes the factorized decision process match native two-phase sequential assignment before any further MAPPO scale-up. Do **not** start locked final testing for a MARL-superiority claim.
