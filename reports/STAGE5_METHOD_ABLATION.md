# Stage 5 — Method ablation

Peak / tight × SOC35 (budget 0.5s):

| Variant | Peak ot_all | Tight ot_all |
| --- | ---: | ---: |
| race_rh (full) | 0.825 | 0.633 |
| race_rh_no_charge_opt | 0.700 | 0.600 |
| race_rh_fixed_07 | 0.725 | 0.633 |
| race_rh_greedy_order | 0.825 | 0.667 |

## Interpretation

- Charge optimization inside the search helps vs no-charge-opt on peak (+0.125).
- Fixed 0.7 inside RACE-RH is worse than free discrete targets on peak.
- Neighborhood relocate does not improve peak vs greedy-order construction; on tight, greedy-order slightly better (0.667 vs 0.633).
- None of the ablations reach greedy_charge_07 peak (0.925) or sf_rh_07 tight (0.733).

The mechanism that helps is **allowing partial targets at all**, not a uniquely powerful RH neighborhood—consistent with Stage 4B’s charging trade-off finding.
