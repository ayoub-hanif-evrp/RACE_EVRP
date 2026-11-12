# RACE-MARL Stage 8.3 — Performance Gap Decomposition

Artifacts: `stage83_gap_metrics.csv`, `stage83_gap_metrics_summary.csv`, recovery + divergence studies.

## Stage ladder (6 development scenarios, seed-0 actors where applicable)

| Stage | Mean OT | Claims | Claim attempts | Idle+pending | Missed feasible | Dup proposals | Held-out op imitation |
|-------|---------|--------|----------------|--------------|-----------------|---------------|----------------------|
| A. Native selective | **0.832** | 26.2 | — | — | — | — | — |
| G. Greedy charge-to-70% | **0.819** | 25.8 | — | — | — | — | — |
| B. Adapter-in-MARL | 0.629 | 18.7 | 35.8 | 28.8 | **0.0** | 11.0 | — |
| B2. Intent bridge | 0.597 | 17.7 | 17.7 | 30.8 | **16.2** | 0.0 | — |
| C. BC+DAgger | 0.629 | 18.7 | 35.8 | 28.8 | 0.0 | 11.0 | **0.883** |
| E. MAPPO A / D / F (seed0) | 0.629 | ~18.7 | ~34 | ~29 | 0–6 | ~10 | **0.883** |

## Where the ~34pp went

| Cause | Evidence |
|-------|----------|
| Pre-8.3 missing service_end/idle decisions | Learned ~0.49 → ~0.63 after parity |
| Batched vs sequential ownership | Divergence traces: first mismatch at simultaneous `op=0` on same rid |
| Intent missed feasible pickups | 16.2 / episode vs adapter 0 |
| Fewer successful claims | Native 26.2 vs factorized ~18.7 |
| Imperfect imitation | Held-out op match 0.883 (not 1.0); still matches teacher OT |
| MAPPO degradation | Seed-0 stable; 3-seed F/E mean 0.564 (seed-2 collapse) |
| Top-K truncation | 0 out-of-K claims on peak (max announced ≤ 5) |

## Answer

Most of the gap vs native is **factorized/batched interface + sequential two-phase mismatch**, not MAPPO alone. After event parity, BC recovers the factorized ceiling (~0.63); it does not recover native ~0.83.
