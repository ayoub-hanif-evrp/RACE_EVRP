# Stage 3A — Novelty decision

## Decision: **A. Energy-commitment-centered RACE**

With a secondary, optional information channel — **not** a joint energy-and-information claim as the default paper thesis.

## Evidence

| Signal | Result |
| --- | --- |
| Energy / SOC binds dispatch | Strong (stress 38→18 at SOC 0.35; charging restored service on baseline) |
| Conservative reserve under bound | Holds after Stage 2.1/3A gates |
| Same-rule communication triad | Periodic +1 served once; fails under low SOC; triggered ≈ none |
| Full vs restricted gap | Largely algorithmic (38 vs 35), not isolated message value |

## Rejected for now

- **B. Joint energy-and-information as core novelty** — not supported: messages do not reliably improve the shared restricted rule enough to justify a TRC contribution centered on communication.
- **C. Reformulate entirely** — unnecessary; energy-feasible online commitments on Casablanca remain a credible TRC-facing problem when compared to strong RH baselines.

## What to build in Stage 3B (next, not now)

A non-learning then possibly learned **risk-aware commitment / reassignment** mechanism under conservative energy bounds, using RH as the strong centralized baseline and restricted no-comm / light-comm as decentralization references.

Do **not** lead with MARL, GNN, or transformer architecture choice.
