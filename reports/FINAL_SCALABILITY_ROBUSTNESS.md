# FINAL SCALABILITY AND ROBUSTNESS

**Raw:** `data/casablanca/online_results/prompt2/race_prompt2_scale.csv` (180/180 OK)  
**Subset:** 6 balanced development scenarios (baseline/peak/tight).

## Fleet size (delay 0)

| Treatment | 3 EV | 5 EV | 10 EV |
|-----------|------|------|-------|
| NONE | 0.8556 | 0.9347 | 0.9514 |
| FULL | 0.8583 | 0.9347 | 0.9514 |
| SELECTIVE_VALID | 0.8583 | 0.9347 | 0.9514 |
| CSC_LITE | 0.8583 | 0.9347 | 0.9514 |

Larger fleets raise OT; CSC-lite tracks selective/full on this subset.

## Initial SOC (3 EV, delay 0)

| SOC | NONE OT | CSC OT | CSC energy kWh |
|-----|---------|--------|----------------|
| 35% | 0.8556 | 0.8583 | 34.05 |
| 60% | 0.9097 | 0.9083 | 35.88 |
| 100% | 0.9042 | 0.9083 | 34.83 |

Energy remains strictly positive.

## Communication robustness

Primary 60-scenario matrix: delays 0/15/30/120; 10% loss @30 s — CSC-lite ≡ matched-wait zero-comm (OT and owners).  
Unit tests cover 100% loss (attempted > 0, delivered = 0).

## Not completed in this milestone

- Separately generated 40/80/160-request demand stress ensembles (compute budget after primary + ablations + fleet/SOC).  
- Full 12-scenario expansion of fleet matrix (6 completed as specified minimum).
