# FINAL STATISTICS PLAN (for Prompt 3 / locked_final)

## Comparison unit

Independent unit = **scenario episode** (not individual requests).

Primary endpoint: `on_time_rate_all = n_on_time / n_requests`.

Also report total on-time counts and requested totals.

## Estimators (locked evaluation)

For each confirmatory contrast:

1. Paired scenario differences ΔOT.  
2. Mean ΔOT in percentage points.  
3. Percentile bootstrap 95% CI (B = 2000, seed = 0) on paired means.  
4. Wins / ties / losses.  
5. Mean attempted recipient bytes; ratio of means vs comparator.  
6. Mean owner Hamming distance (executed ownership maps).  
7. Energy consumed, charge delivered, decision ms, safety counts.

## Confirmatory vs exploratory

**Confirmatory (preregister before locked_final):**

- H vs A @0 s (service + bytes)  
- H vs B @0 s (noninferiority / efficiency)  
- H vs I @15 and @30 s (null delayed information use)  
- H vs G @15 and @30 s (speculative-deferral harm avoided)

**Explormatory:** regime splits, fleet/SOC, loss pilots, ablations.

## Noninferiority margin

Absolute OT margin **0.02** (2 pp) was recorded in prior closeout/dev scripts and has **exploratory exposure** to development data.

Before locked_final: re-declare this margin with that history disclosed.  
Do **not** treat development-tuned margins as naive preregistration.

Noninferiority of H to A does **not** prove communication usefulness.  
Beating G under delay does **not** prove usefulness vs I.

## Pareto

Plot mean OT vs mean attempted bytes including A (zero communication).  
At positive delay, equal-OT policies with unused bytes are dominated.
