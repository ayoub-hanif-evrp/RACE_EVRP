# RACE PASS 1 — Development Pilot Results

**Artifacts:** `data/casablanca/online_results/race_pass1_pilot.csv`, `race_pass1_pilot_summary.json`, `race_pass1_matched_budget.json`, `race_pass1_pilot_run.log`  
**Ensemble:** 6 development scenarios via `resolve_eval_dirs()`; 3 EVs; SOC=0.35. **Not** locked final.  
**Controller:** frozen native cooperative routing + charge-to-70%.

Matched budget calibrated on selective (delay=0): **129** recipient messages / episode (mean selective bytes ≈ 59089).

## Delay = 0 — primary communication comparison

| Treatment | Mean OT | On-time / req | Mean msgs | Mean bytes |
|-----------|---------|---------------|-----------|------------|
| A none | 0.821 | **154 / 192** | 0 | 0 |
| B full | **0.832** | **157 / 192** | 643 | 253946 |
| C periodic (300 s) | **0.835** | **157 / 192** | 455 | 164203 |
| D random matched | 0.815 | 153 / 192 | **119** | 49396 |
| E selective | **0.832** | **157 / 192** | **129** | **59089** |
| F certified | **0.832** | **157 / 192** | 129 | 65814 |
| G ecom | **0.832** | **157 / 192** | 129 | 63227 |

Paired vs selective (6 scenarios): full / certified / ecom = **0 wins / 6 ties / 0 losses** on OT; owners identical for F and G vs E. Random matched: 1W/2T/3L.

### Byte ratios vs full (delay 0)

| Treatment | Ratio of mean bytes | Mean of scenario ratios |
|-----------|---------------------|-------------------------|
| E selective | 0.233 | 0.348 |
| F certified | 0.259 | 0.387 |
| G ecom | 0.249 | 0.372 |
| D random matched | 0.195 | 0.318 |
| C periodic | 0.647 | 0.558 |

These two statistics differ; both are reported deliberately.

### ECOM counters (delay 0)

Mean `n_ecom_proved` = **0**; mean `n_ecom_fallback` ≈ 65. After public-roster correctness, PROVED dominance almost never fires on this set (heuristic intervals + coverage discipline). Behavior is mostly FALLBACK/HEURISTIC, not unjustified A-labels.

## Delay = 30 s (loss = 0)

| Treatment | Mean OT | Mean msgs | Mean bytes |
|-----------|---------|-----------|------------|
| A none | **0.801** | 0 | 0 |
| B full | 0.761 | 840 | 333825 |
| C periodic | **0.825** | 490 | 176958 |
| D random matched | 0.765 | 122 | 52751 |
| E selective | 0.775 | 228 | 103395 |
| F certified | 0.779 | 182 | 91601 |
| G ecom | 0.775 | **174** | **84533** |

Under 30 s delay, **no communication and periodic can beat full/selective on OT** on this small set — delayed bids are not free. ECOM ≈ selective OT with fewer messages/bytes than selective.

Packet loss 10% (full / selective / ecom): OT ≈ 0.77 for all three; ecom still lowest traffic among them.

## Delay = 120 s

| Treatment | Mean OT | Mean msgs | Mean bytes |
|-----------|---------|-----------|------------|
| A none | **0.799** | 0 | 0 |
| B full | 0.779 | 896 | 354818 |
| E selective | 0.786 | 277 | 127264 |
| G ecom | 0.783 | **145** | **71717** |

ECOM cuts selective traffic roughly in half at 120 s with nearly matched OT (selective +0.003 mean OT).

## Correctness repairs verified in pilot

1. Periodic no longer silent (positive `periodic_broadcast_s`).
2. Matched random ≈ selective message budget (≈119 vs 129; invalidations charged).
3. Delayed full completes (0/30/120) without hang; coalesce/supersede active.
4. Certified/ecom no longer explode under delay (cascade guard on `reason==message`).

## What failed / did not hold

1. **ECOM does not improve OT vs selective at delay 0** (identical service and owners).
2. **PROVED rate ≈ 0** after honest roster coverage — no empirical “certified unique winner” advantage on this pilot.
3. **ECOM bytes ≥ selective at delay 0** (certificate metadata overhead).
4. Under delay, **none/periodic can outperform chatty protocols** on OT — multi-agent messaging is not unconditionally valuable.
