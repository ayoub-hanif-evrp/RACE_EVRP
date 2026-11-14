# Expanded Development Evaluation (60 scenarios)

**Ensemble:** `data/casablanca/evaluation_v1/default` (60 scenarios). **Not** `locked_final`.  
**Artifacts:** `race_expanded_dev.csv`, `race_expanded_dev_summary.json`, `race_devval_matched_budget.json`, `race_devval_noninferiority_margin.json`  
**Calibration:** train scenarios only → matched msgs=105, matched bytes≈47985.  
**Pre-registered noninferiority margin:** **2.0 percentage points** absolute OT vs comparator (frozen before expanded eval).  
**Primary metrics:** on-time rate; recipient transmissions; serialized bid bytes.  
**Fleet:** 3 EVs, SOC=0.35. Wall ≈15–19 s/episode.

## Delay = 0 (n=60)

| Treatment | Mean OT | Mean msgs | Mean bytes |
|-----------|--------:|----------:|-----------:|
| A none | 0.8339 | 0 | 0 |
| B full | **0.8438** | 530 | 210128 |
| C periodic | 0.8421 | 370 | 133443 |
| D random byte-matched | 0.8382 | 96 | 40868 |
| **E selective** | **0.8438** | **112** | **51531** |
| G ecom | **0.8438** | 112 | 55123 |
| H selective_deadline | **0.8438** | 112 | 51531 |
| I ecom_deadline | **0.8438** | 112 | 55123 |

Paired vs selective: full/ecom/deadline = **0/60/0** (identical OT). Selective vs none: +0.99 pp (95% CI −0.06 to +2.03); W/T/L = 19/31/10.  
Battery reserve violations = 0 for all. PROVED certificates ≈ 0.

**Pareto at delay 0:** selective dominates ecom (same OT, fewer bytes). Full matches OT at ~4× bytes.

## Delay = 30 (n=60)

| Treatment | Mean OT | Mean bytes | Mean peer defers |
|-----------|--------:|-----------:|-----------------:|
| A none | **0.8328** | 0 | 0 |
| B full | 0.7699 | 310261 | 72.9 |
| E selective | 0.7765 | 106309 | 103.2 |
| G ecom | 0.7764 | 84543 | 73.4 |
| **H selective_deadline** | **0.8315** | 54523 | **0** |
| **I ecom_deadline** | **0.8315** | **46396** | **0** |

Paired OT vs selective: H/I **+5.50 pp** (95% CI +3.46 to +7.54); W/T/L 35/19/6.  
Paired OT vs none: H/I **−0.13 pp** (95% CI −0.66 to +0.41) — within 2 pp noninferiority margin; W/T/L 4/54/2.

## Delay = 120 (n=60)

| Treatment | Mean OT | Mean bytes | Mean peer defers |
|-----------|--------:|-----------:|-----------------:|
| A none | 0.8225 | 0 | 0 |
| B full | 0.7869 | 291177 | 28.7 |
| E selective | 0.8106 | 102983 | 45.4 |
| G ecom | 0.7901 | 68375 | 30.1 |
| **H selective_deadline** | **0.8289** | **44206** | **0** |
| **I ecom_deadline** | **0.8289** | 47122 | **0** |

Paired OT vs selective: H/I **+1.83 pp** (95% CI +0.49 to +3.18); W/T/L 24/27/9.  
Paired OT vs none: H/I **+0.64 pp** (95% CI −0.22 to +1.50) — within 2 pp margin; W/T/L 14/37/9.

## Interpretation

1. Unmodified ECOM remains non-superior to selective at delay 0 and harmful vs none under delay.
2. **Delay-aware selective / ecom_deadline** (commit-now + stale-peer distrust) removes harmful deferrals and recovers service under delay, with large byte cuts vs selective.
3. At delay 0 the refinement is inert (identical to selective).
4. Zero reserve/exhaustion violations observed in this matrix.

## Runtime

Mean wall ≈ 14–19 s per episode on the evaluation machine; 1200 expanded jobs completed with 4 workers.
