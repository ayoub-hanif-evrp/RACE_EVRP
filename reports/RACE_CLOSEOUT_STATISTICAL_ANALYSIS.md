# Closeout Statistical Analysis

**Unit:** independent scenario episode (n=60 development scenarios).  
**Primary metric:** `on_time_rate_all`.  
**Secondary:** recipient messages, serialized bid bytes, assign wait, peer defers.  
**Pre-registered noninferiority margin:** 2.0 percentage points absolute OT (`race_closeout_noninferiority_margin.json`).  
**Intervals:** unadjusted paired mean ± 1.96×SEM (approximate 95% CI). Equal means ≠ equivalence.

## Delay 0 — paired vs selective

| Treatment | Mean ΔOT | 95% CI | W/T/L |
|-----------|---------:|--------|------:|
| none | −0.0062 | [−0.0175, +0.0050] | 14/29/17 |
| full | 0 | [0, 0] | 0/60/0 |
| event_triggered | 0 | [0, 0] | 0/60/0 |
| ecom | 0 | [0, 0] | 0/60/0 |
| selective_deadline (H) | 0 | [0, 0] | 0/60/0 |
| central greedy | −0.0676 | [−0.0873, −0.0480] | 5/19/36 |

Selective vs none: +0.0062 [−0.0050, +0.0175] — **not** a significant service gain; communication savings are the delay-0 story.

## Delay 30 — paired

| Contrast | Mean ΔOT | 95% CI | W/T/L | Noninf (2pp)? |
|----------|---------:|--------|------:|---------------|
| H − selective | **+0.0693** | [+0.0465, +0.0921] | 37/18/5 | N/A (superior) |
| H − none | −0.0025 | [−0.0109, +0.0059] | 8/42/10 | **Yes** (CI above −0.02) |
| selective − none | −0.0718 | [−0.0928, −0.0508] | 4/18/38 | No |

## Delay 120 — paired

| Contrast | Mean ΔOT | 95% CI | W/T/L | Noninf (2pp)? |
|----------|---------:|--------|------:|---------------|
| H − selective | **+0.0335** | [+0.0195, +0.0475] | 32/22/6 | N/A (superior) |
| H − none | −0.0053 | [−0.0159, +0.0054] | 10/35/15 | **Yes** |
| selective − none | −0.0387 | [−0.0518, −0.0257] | 3/24/33 | No |

## Safety

Battery reserve violations = 0 and exhaustions = 0 across the closeout matrix.

## Interpretation limits

- Development ensemble only; locked_final untouched.  
- Noninferiority of H vs none is supported under the pre-registered 2 pp margin at 30/120 s, not statistical equivalence to zero.  
- Delay-0 improvement of H over selective is **absent** (identical).
