# FINAL DEVELOPMENT EVALUATION — Prompt 2

**Ensemble:** `data/casablanca/evaluation_v1/default` (60 scenarios)  
**Locked-final:** not used  
**Raw:** `data/casablanca/online_results/prompt2/race_prompt2_primary.csv` (2100/2100 OK)  
**Paired:** `.../race_prompt2_primary_paired.json`  
**Figures:** `reports/figures/prompt2/pareto_delay_{0,30}.png`

## Configuration

- 3 EVs, SOC 35%, frozen Casablanca traffic  
- Delays 0 / 15 / 30 / 120 s; primary loss 0%; loss pilot 10% @ 30 s (subset)  
- Primary cost metric: **attempted recipient bid bytes** (includes drops)  
- Energy: `energy_consumed_kwh` / `energy_delivered_kwh` (nonzero verified)

## Mean on-time rate (loss = 0, n = 60)

| Treatment | 0 s | 15 s | 30 s | 120 s |
|-----------|-----|------|------|-------|
| A NONE_NOW | 0.8361 | 0.8361 | 0.8361 | 0.8361 |
| B FULL | 0.8424 | 0.7601 | 0.7758 | 0.8308 |
| C PERIODIC | 0.8361 | — | — | — |
| D RANDOM_BYTE_MATCHED | 0.8361 | — | — | — |
| E EVENT_TRIGGERED | 0.8424 | — | — | — |
| F SELECTIVE_LEGACY | 0.8424 | 0.7571 | 0.7643 | 0.7974 |
| G SELECTIVE_VALID_PEER | 0.8424 | 0.7561 | 0.7700 | 0.8308 |
| **H CSC_LITE** | **0.8424** | **0.8350** | **0.8336** | **0.8308** |
| I MATCHED_WAIT_ZERO_COMM | 0.8361 | 0.8350 | 0.8336 | 0.8308 |
| J MESSAGE_PLACEBO | 0.8361 | 0.8350 | 0.8336 | 0.8308 |

Cells marked — were not in the positive-delay priority set (declared omission).

## Mean attempted bid bytes (loss = 0)

| Treatment | 0 s | 15 s | 30 s | 120 s |
|-----------|-----|------|------|-------|
| A | 0 | 0 | 0 | 0 |
| B | 219836 | 345541 | 327556 | 251260 |
| H | 55793 | 63238 | 64596 | 48166 |
| I | 0 | 0 | 0 | 0 |
| J | 50652 | 63238 | 64596 | 48166 |
| G | 55793 | 139581 | 264677 | 48166 |

## Key paired results (H = CSC-lite; bootstrap 95% CI)

| Contrast | Delay | ΔOT (pp) | 95% CI | W/T/L | Owner Hamming |
|----------|-------|----------|--------|-------|---------------|
| H vs A | 0 | +0.62 | [−0.49, +1.72] | 17/29/14 | 11.15 |
| H vs B | 0 | 0.00 | [0, 0] | 0/60/0 | 0 |
| H vs G | 0 | 0.00 | [0, 0] | 0/60/0 | 0 |
| H vs I | 0 | +0.62 | [−0.49, +1.72] | 17/29/14 | 11.15 |
| H vs I | 15 | **0.00** | [0, 0] | 0/60/0 | **0** |
| H vs I | 30 | **0.00** | [0, 0] | 0/60/0 | **0** |
| H vs G | 15 | **+7.89** | [+5.56, +10.24] | 43/15/2 | 15.18 |
| H vs G | 30 | **+6.36** | [+4.15, +8.75] | 36/19/5 | 15.05 |
| H vs B | 15 | +7.49 | [+5.18, +9.86] | 43/14/3 | 14.80 |
| H vs F | 120 | +3.35 | [+2.00, +4.75] | 32/22/6 | 14.00 |
| Loss 0.1 @30: H vs I | 30 | 0.00 | [0, 0] | 0/60/0 | 0 |

Byte ratio means @0 s: H/B ≈ 55793/219836 ≈ **0.254** (−74.6% vs full).

## Physical metrics (H @0 s)

- Mean energy consumed ≈ 34.4 kWh (min across OK rows > 10 kWh)  
- Mean decision latency ≈ 116.5 ms; n_decisions > 0 always  
- Reserve / exhaustion / stranding sums: see summary CSV (primary run: no widespread stranding)

## Interpretation (RQ1–RQ3)

1. **Zero delay:** CSC-lite is **service-tied with full/selective** and uses ~75% fewer attempted bytes than full. Mean +0.62 pp vs none is **not** CI-significant; claim is **communication noninferiority / efficiency**, not proven service superiority.  
2. **Positive delay:** CSC-lite **prevents speculative-deferral losses** vs G/F/B (+6–8 pp @15–30 s) and is **behaviorally identical** to matched-wait zero-comm and message placebo (owner Hamming 0).  
3. **Causality:** Peer offers change ownership at delay 0 (Hamming 11.15 vs I/A). Under delay, delivered offers do **not** change claims under CSC-lite.  
4. **Pareto:** At delay 0, H lies on the empirical frontier with B/E/F/G (same OT, far fewer bytes than B). At delay 30, H/I/J dominate G/F/B on OT; among them **I dominates H/J on bytes** (0 vs ~65 kB) for equal OT.

## Caveats

- Development ensemble (prior exposure).  
- `C_PERIODIC` logged 0 task-bid attempted bytes (state-periodic path).  
- `D_RANDOM_BYTE_MATCHED` realized ~2 kB vs predeclared ~55 kB selective mean — **not** a valid byte-matched comparator as executed; do not claim matching.  
- Demand 40/80/160 stress generator not executed (primary + ablations + fleet/SOC completed first).
