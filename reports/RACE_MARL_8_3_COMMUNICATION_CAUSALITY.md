# RACE-MARL Stage 8.3 — Communication Causality

Artifacts: `stage83_causality_*.csv/json`, `stage83_service_vs_bytes.csv`.

## Non-learning (development scenarios, delay=0)

| Method | Mean OT | Mean bid bytes |
|--------|---------|----------------|
| nl_none | 0.821 | 0 |
| nl_selective | **0.832** | ~4.8e4 |
| nl_full | **0.832** | ~2.2e5 |
| greedy_charge70 | 0.819 | 0 |

Selective matches full OT at ~4.6× lower bytes than full. Selective vs none OT Δ ≈ **+0.011** on this set (ownership Hamming still material; see deltas CSV).

At 30s delay, selective OT ≈ 0.801 (modest degradation; bids often still influence owners).

## MARL intent bridge (factorized)

| Method | Mean OT | Bytes |
|--------|---------|-------|
| marl_intent A/D/E | **0.597** | 0 / ~1.3e4 |

Intent-bridge OT is flat across A/D/E — **no causal service gain from communication** under the factorized interface on the 6-scen mean, despite nonzero bytes for D/E.

## Interpretation

1. Non-learning selective protocol remains the only communication result with matched service and lower bandwidth.
2. Factorized MARL intent does not yet show a service–bandwidth trade-off; communication volume ≠ allocation effect.
3. Learned RACE-MARL must not claim a causal communication advantage until F≠A/C on service with matched budgets.
