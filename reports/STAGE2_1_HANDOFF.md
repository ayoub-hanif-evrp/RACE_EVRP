# Stage 2.1 — Handoff

## Status: COMPLETE (acceptance conditions met)

| Deliverable | Path |
| --- | --- |
| Correctness audit | `reports/STAGE2_1_CORRECTNESS_AUDIT.md` |
| Energy safety | `reports/STAGE2_1_ENERGY_SAFETY.md` |
| Information architecture | `reports/STAGE2_1_INFORMATION_ARCHITECTURE.md` |
| Baseline comparison | `reports/STAGE2_1_BASELINE_COMPARISON.md` |
| Metrics / traces | `data/casablanca/online_results/stage2_1_*` |
| Runner | `scripts/run_stage2_1_baselines.py` |
| Adversarial tests | `tests/test_stage2_1_adversarial.py` |

`casablanca_release_v1` unchanged. No PPO/GNN/MARL.

## Scientific implication for Stage 3 (design only — not implemented)

- **Energy-feasible commitments** are justified: low SOC and δ change dispatch; corrected safety holds under the bound; charging matters at low SOC.
- **Communication / partial info** is now a fair comparison: peak stress shows a real serve-rate gap (38 vs 35). Mild baseline still weak for that claim.
- Prefer designing RACE around **energy-risk + commitment** first, with decision-relevant messaging as a joint mechanism only where restricted-info loss is measurable (stress-like regimes).
- Compare future methods against corrected **full-info RH** and **restricted cooperative** baselines, not Stage-2’s leaked “limited” policy.

## STOP

Do not implement the novel RACE learning method in this stage.
