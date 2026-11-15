# Closeout Expanded Development Results (Corrected Timing)

**Ensemble:** 60 scenarios in `evaluation_v1/default` (development evidence, **not** locked_final).  
**Artifacts:** `race_closeout_expanded_dev.csv`, `race_closeout_expanded_dev_summary.json`, `race_closeout_matched_budget.json`, `race_closeout_noninferiority_margin.json`  
**Noninferiority margin (pre-registered):** 2.0 pp absolute OT vs selective / vs none as noted.  
**Fleet:** 3 EVs · SOC 35% · fair physical decisions · train-calibrated byte budget.

## Delay = 0 (n=60)

| Treatment | Mean OT | Mean msgs | Mean bytes | Mean phys claims |
|-----------|--------:|----------:|-----------:|-----------------:|
| A none | 0.8361 | 0 | 0 | 173.9 |
| B full | **0.8424** | 509 | 202029 | 174.0 |
| C periodic | 0.8361 | 414 | 149421 | 173.9 |
| D random byte-matched | 0.8396 | 101 | 42910 | 174.1 |
| **E event_triggered** | **0.8424** | **113** | **51833** | 174.0 |
| **F selective** | **0.8424** | **113** | **51833** | 174.0 |
| G ecom | **0.8424** | 113 | 55453 | 174.0 |
| H selective_deadline | **0.8424** | 113 | 51833 | 174.0 |
| I central greedy (full info) | 0.7747 | 0 | 0 | — |

Paired vs selective: event_triggered / full / ecom / H = **0/60/0**.  
Selective vs none: +0.62 pp (95% CI −1.75 to +1.75) — positive mean, not significant.  
**Event-triggered matches selective OT and bytes at delay 0** → contest/expiry refreshes add no delay-0 value here.  
ECOM uses more bytes for equal OT. Reserve violations = 0. PROVED ≈ 0.

## Delay = 30 (n=60) — corrected none wait=0

| Treatment | Mean OT | Mean bytes | Assign wait | Peer defers |
|-----------|--------:|-----------:|------------:|------------:|
| **A none** | **0.8361** | 0 | **0** | 0 |
| B full | 0.7765 | 309169 | 37.5 | 40.6 |
| E event_triggered | 0.7726 | 88374 | 37.5 | 41.6 |
| F selective | 0.7643 | 254757 | 37.5 | 45.1 |
| G ecom | 0.7765 | 97391 | 37.5 | 41.9 |
| **H selective_deadline** | **0.8336** | **59883** | 30 | **0** |

- None OT **unchanged** vs delay 0 (timing confound removed).  
- H vs selective: **+6.93 pp** (95% CI +4.65 to +9.21); W/T/L 37/18/5.  
- H vs none: **−0.25 pp** (95% CI −1.09 to +0.59) — within 2 pp noninferiority; W/T/L 8/42/10.  
- Unmodified selective/full/ecom/event_triggered all **significantly worse than none**.

## Delay = 120 (n=60)

| Treatment | Mean OT | Mean bytes | Assign wait | Peer defers |
|-----------|--------:|-----------:|------------:|------------:|
| **A none** | **0.8361** | 0 | **0** | 0 |
| B full | 0.7972 | 279685 | 120 | 18.4 |
| E event_triggered | 0.7958 | 66914 | 120 | 19.1 |
| F selective | 0.7974 | 163004 | 120 | 15.6 |
| G ecom | 0.7962 | 73737 | 120 | 19.5 |
| **H selective_deadline** | **0.8308** | **44837** | 60 | **0** |

- H vs selective: **+3.35 pp** (95% CI +1.95 to +4.75); W/T/L 32/22/6.  
- H vs none: **−0.53 pp** (95% CI −1.59 to +0.54) — within 2 pp margin.  
- Event_triggered ≈ selective OT with **fewer** bytes under delay (selective contest refresh is costly).

## Diagnostic vs historical PASS1 ranking

| Claim from PASS1 (confounded) | After correction |
|-------------------------------|------------------|
| None OT falls under delay | **False** — none OT flat once wait=0 |
| Communication delay alone hurts none | **False** — hurt was forced assign wait |
| Selective under delay trails none | **Still true** — deferrals + waiting for peers |
| Deadline-aware selective recovers | **Confirmed** on 60 scenarios |

## Pareto notes

- **Delay 0:** selective / event_triggered share the best restricted OT–bytes point; ecom dominated; full matches OT at ~4× bytes.  
- **Delay 30/120:** H is the only communicating treatment near none’s OT with substantial byte use below selective/full.
