# Stage 6 — Why RACE-RH underperforms (failure explanation)

This is a diagnosis task. **No new policy was implemented.**

## 1. Search almost never improves the incumbent

Across all **12** Stage 6 RACE-RH runs (`stage6_final_comparison.csv`):

| Counter | Observed |
| --- | --- |
| `n_chose_optimized` | **0** on every scenario |
| `n_chose_incumbent` | typically 23–63 per episode |
| `policy_timeouts` | mean **22.6**; peak release runs ~41–43 |
| `policy_runtime_s` | mean **23.1** s; peak up to ~45 s |

The optimizer spends its budget evaluating charge/route variants and then keeps the incumbent (or safety fallback). We pay computational cost without selecting improved plans.

## 2. Charging readiness already explains much of the recoverable gap

Stage 5.1 showed that enabling readiness charging recovered pickups for RACE-RH versus a no-readiness control. Stage 6 keeps readiness on. Even so, greedy charge-to-70% remains equal or better on most paired SOC35 scenarios (5 greedy wins, 6 ties, 1 RACE win).

Interpretation: the valuable operational idea is **keep vehicles charge-ready**, not the expensive joint search.

## 3. Matched peak example (release `peak_stress_seed2`, SOC35)

| Policy | On-time | Runtime | Timeouts | Optimized chosen |
| --- | ---: | ---: | ---: | ---: |
| greedy→70% | **36/40** | ~0 | 0 | n/a |
| SF-RH→70% | 34/40 | ~0 | 0 | — |
| RACE-RH | 33/40 | 34.0 s | 43 | **0** |

Where greedy serves and RACE misses, the difference is consistent with depot readiness / charge timing under a myopic commitment model, not with RACE discovering a superior committed route that greedy cannot. Because optimized plans are never selected, route-order “improvements” from search do not enter the executed policy.

## 4. Objective mismatch

RACE-RH’s search scores feasible commitments on **currently known** requests under hard deadlines and energy bounds. That is not identical to maximizing expected end-of-day on-time pickups under unknown future arrivals. Idle charging, location preservation, and avoiding premature commitment can matter before the next request exists—behaviors greedy→70% approximates cheaply via a fixed target SOC.

## 5. Simulator defect vs algorithmic limitation

Stage 5.1 repaired SERVING/CHARGING projection and readiness bugs (Decision B: correct implementation, no advantage). Stage 6, on the repaired simulator, still shows:

- timeouts and incumbent lock-in;
- no optimized-plan selections;
- paired OT not better than greedy→70%.

**Classification:** algorithmic / problem-formulation limitation under the current online objective and search budget — **not** an unresolved simulator defect.

## 6. Dataset size is secondary

Expanding to `evaluation_v1` (more synthetic episodes) did not reverse the ranking. Small release size makes CIs wide, but the failure mode (0 optimized selections + high timeout cost) is structural.
