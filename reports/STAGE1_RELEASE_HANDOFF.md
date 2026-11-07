# Stage-1 release handoff

Benchmark: **`casablanca_release_v1`**  
Generator: **`0.3.1`**  
Verification: `scripts/verify_benchmark_release.py` → **ok=true** (full mode)  
Pytest: **36 passed**

## Fixed in this release

| Issue | Resolution |
| --- | --- |
| Boundary repaired but network/candidates/weights stale | Full rebuild via `build_casablanca_release.py` |
| Wrong README order (weights before candidates) | Corrected + enforced freshness checks |
| Stale `reference_schedule` on uncertified scenarios | Atomic scenario IO; purge obsolete witnesses |
| Leftover partial on certified scenarios | Removed when certified |
| Legacy generator 0.2.0 `baseline_seed42` | Removed from release |
| Mixed-version manifests | Active release filter by generator 0.3.1 |

## Regenerated facts (do not assume prior counts)

- Candidates: **47,193** (accessible 44,892)  
- Eligible zones: **17**; positive weight: **16**  
- Ahl Laghlam: accessible but ~0 weight (documented warning)  
- SCC exclusion: **18.3%** nodes  

## Freeze decision

**Engineering release integrity: PASS** for `casablanca_release_v1`.

**Scientific readiness for a top-tier algorithmic contribution: NOT claimed.** Energy/payload still non-binding on certified baselines; demand remains synthetic; traffic remains an approximation.

## Stop line

Do **not** start multi-agent simulation, PPO, GNN, or MARL from this checkpoint. Next stage is problem formulation and novelty design.
