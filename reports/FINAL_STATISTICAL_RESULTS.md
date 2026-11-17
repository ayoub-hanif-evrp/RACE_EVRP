# FINAL STATISTICAL RESULTS (Prompt 3)

Procedure: paired scenario differences; percentile bootstrap B=2000, seed=0; unit = episode. Source: `final_locked_paired.json`. Noninferiority margin 2 pp with disclosed exploratory history (`FINAL_STATISTICS_PLAN.md`).

## Confirmatory primary comparisons

### 1. H vs B @ 0 s (service + bytes + NI)

| Statistic | Value |
|---|---|
| n | 30 |
| Mean OT H / B | 83.42% / 83.42% |
| Mean ΔOT | **+0.00 pp** [0.00, 0.00] |
| One-sided 5% lower bound | 0.00 pp |
| NI vs −2 pp margin | **Noninferior** (lower bound ≫ −2) |
| Wins/ties/losses | 0/30/0 |
| Owner Hamming | 0.00 |
| Byte ratio (H/B means) | **0.239** (−76.1% attempted bytes) |

Interpretation: CSC-lite preserves full-bidding zero-delay service while cutting ~76% of attempted recipient bytes.

### 2. H vs A @ 0 s

| Statistic | Value |
|---|---|
| Mean ΔOT | **+0.61 pp** [−0.42, +1.64] |
| W/T/L | 8/17/5 |
| Owner Hamming | 9.90 |

Interpretation: Point estimate favors communication, but CI includes zero — **not proven superior** to no communication on locked_final.

### 3. H vs I @ 30 s

| Statistic | Value |
|---|---|
| Mean ΔOT | **+0.00 pp** [0.00, 0.00] |
| W/T/L | 0/30/0 |
| Owner Hamming | 0.00 |

Interpretation: Exact episode-level equality with matched-wait zero-comm. Delayed peer bids confer **no allocation benefit** once CSC-safe claim is used.

### 4. H vs G @ 30 s

| Statistic | Value |
|---|---|
| Mean ΔOT | **+8.33 pp** [+5.64, +11.28] |
| W/T/L | 21/8/1 |
| Owner Hamming | 14.27 |
| Byte ratio H/G | 0.209 |

Interpretation: Avoiding deferral to nonbinding delayed offers prevents large service losses. This is a **safety-of-assumption** result, not proof that messages add value vs I.

### 5. H vs I @ 120 s

Exact equality (ΔOT = 0, Hamming = 0). Delayed no-peer equivalence continues.

### 6. H vs E @ 0 s

Exact equality (ΔOT = 0, Hamming = 0, byte ratio = 1.0). **CSC-lite shows no distinct zero-delay efficiency advantage over event-triggered** on this locked set.

## Additional locked contrasts (exploratory / secondary)

| Contrast | ΔOT pp [CI] | Note |
|---|---|---|
| H vs F @ 0 | 0.00 | Identical selective traffic |
| H vs C @ 0 | 0.00; byte ratio 1.13 | Periodic matches OT |
| H vs D @ 0 | −0.14 [−1.25, +0.86] | Random slightly higher OT (NS) |
| H vs B @ 30 | +7.97 [+5.08, +11.03] | Full collapses under delay |
| H vs F @ 30 | +7.94 [+5.36, +10.61] | Legacy speculative deferral |
| H vs A @ 30 | +0.22 [−0.44, +0.94] | CI includes 0 |
| H vs F @ 120 | +2.39 [+0.64, +4.22] | Legacy still harmed |
| H vs G/B @ 120 | 0.00 | Aligns with CSC/valid-peer/full |
| J vs I (all delays) | 0.00 | Placebo messages unused |

## Multiplicity

Confirmatory set is the six comparisons above. Favorable exploratory contrasts (e.g. H vs F @120) are not promoted to primary claims. Null delayed-information results are reported with equal prominence.
