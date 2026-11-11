# RACE-MARL Stage 8.2 — Novelty Decision

## Candidate claim

Energy-certified, decision-relevant communication under irreversible online pickup commitments for electric fleets.

## Established

- Code-level F≠D mechanism (contest/energy-cert gate).
- Correct B/C on-policy treatment; clean E ablation; bid-before-commit.
- **Non-learning** causality: withheld/delayed certificates change owners and OT; selective matches full OT at much lower bytes.

## Not established for the *learned* method

On validation, learned A/B/C/F remain ≈ 0.49 OT. F’s lower byte use vs B does not buy service. No Gate-3 proof that **learned** selective energy certificates beat matched random under equal decision opportunities.

## Decision

**Provisional / negative for a TR Part C methodological claim about learned RACE-MARL selective communication.**

Viable paper angles if recovery fails further:

1. Non-learning RACE-COMM (selective energy bids, delay robustness, byte–service curve) as primary contribution.
2. Honest negative / open MARL result: corrected MAPPO + BC still does not close the cooperative teacher gap under restricted information.

Do **not** claim novelty for generic learned message gating.
