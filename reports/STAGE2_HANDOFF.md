# Stage 2 — Handoff

## Done

| Deliverable | Path |
| --- | --- |
| Mathematical formulation | `reports/STAGE2_MATHEMATICAL_FORMULATION.md` |
| Event-driven simulator | `src/race_casablanca/sim/` |
| Coordination (registry + delayed messages) | `src/race_casablanca/coordination/` |
| Baselines A/B/C | `src/race_casablanca/policies/` |
| Benchmark entry | `scripts/run_online_baselines.py`, `scripts/finish_stage2_baselines.py` |
| Tests | `tests/test_online_simulator.py`, `test_online_invariants.py`, `test_online_policies.py` |
| Validation / results / novelty | `reports/STAGE2_*.md` |
| Metrics artifact | `data/casablanca/online_results/stage2_baseline_metrics.*` |

Frozen dataset `casablanca_release_v1` / generator `0.3.1` **unchanged**.  
Light release verify: **PASS** (0 errors, Ahl Laghlam warning).

## Explicitly not done (stop conditions)

- No PPO / GNN / transformer / MARL / policy-gradient training  
- No final “RACE algorithm”  
- No Chinese / LaDe / EVMobilityBench data  
- No Casablanca map rebuild  

## Evidence summary for method design

1. Online simulator + three non-learning baselines are operational (synthetic + Casablanca baseline/peak-stress).  
2. Energy becomes strongly decision-relevant under low SOC / δ (peak stress 31/40 → 12/40 served) — not under default full-SOC release.  
3. Limited information did **not** reduce serve rate vs full-info on tested scenarios; a communication-centric claim needs different metrics or harder info regimes.  
4. Literature niche remains **decision value of communicating energy-feasible commitments**, not “add MARL+attention.”

## Recommended next step (Stage 3 design only after review)

Use `STAGE2_BASELINE_RESULTS.md` + `STAGE2_RESEARCH_NOVELTY.md` to choose:

- **Coordination-centered** RACE if stress runs show clear full-info vs restricted gaps; or  
- **Energy-commitment-centered** RACE if low-SOC/δ regimes dominate; or  
- **Joint** only if both effects are measurable and ablatable against the Stage-2 baselines.

Do not pick a neural architecture before that choice.
