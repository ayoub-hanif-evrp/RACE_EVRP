# RACE-MARL Stage 8.3 — Teacher Parity

## Experiments

1. **Native** `RaceCooperativePolicy` (standalone).
2. **Adapter** `CooperativeTeacherAdapter` in MARL (`env.step`).
3. **Native bridge execute** — sequential mutating `on_decision` at MARL epochs.
4. **Native bridge intent** — soft-assign labels + `env.step`.

Deep traces: `stage83_teacher_divergence_*.csv/json` over **normal / peak / tight**, **SOC=0.35**, **delay ∈ {0, 30s}** (24 comparisons).

## Aggregate OT

| Method | Mean OT |
|--------|---------|
| Native selective | **0.832** |
| Native bridge execute | **~0.821** |
| Adapter-in-MARL | **0.629** |
| Intent bridge | **0.597** |

## Deep divergence (Task 2)

Summary (`stage83_teacher_divergence_summary.json`):

| Compare | Mean OT gap vs native | Owner divergences / 12 |
|---------|----------------------|-------------------------|
| adapter | 0.188 | 11 |
| intent | 0.219 | 11 |

### Example request-level explanation (peak_stress_seed101, delay=0)

- First ownership mismatch: `peak_stress-101-0001` — native owner **V2**, adapter/intent owner **V1**.
- First conflicting claim epoch: `t≈27988`, reason=`request_release`; all three vehicles propose `op=0` on the sole available task; batched resolution awards **V1**, whereas sequential native awards **V2**.
- Downstream: 5 on-time completion ID differences.

This is the dominant interface gap: **simultaneous duplicate proposals** vs native sequential two-phase assignment — not missing `service_end` returns (those are fixed).

## Interpretation

- Adapter and intent are **not** equivalent to `RaceCooperativePolicy`.
- Intent≈adapter on peak when soft-assign+charge fixes apply; mean intent still slightly weaker (more missed feasible pickups — see gap metrics).
- BC must target a declared teacher (intent/adapter), not claim native equivalence.
