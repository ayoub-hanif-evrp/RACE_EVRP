# Stage 5.1 — Binding scientific decision

## Outcome: **B — Correct implementation but no methodological advantage**

### Evidence (train, Stage 5.1 canonical)

Peak SOC35:

| Policy | served / 40 |
| --- | ---: |
| greedy_charge_07 | **36** |
| sf_rh_07 / charge_aware | 34 |
| race_rh (repaired) | 33 |
| race_rh_no_ready | 30 |
| greedy_always_full | 31 |
| greedy_adaptive | 29 |

Tight SOC35: greedy_07 / sf_rh_07 / charge_aware **21/30**; race_rh **20/30**.

Readiness helps (+3 on peak vs no-ready) but does not close the gap to greedy charge-to-0.7.

Computation: RACE-RH is slower, timeouts frequent; almost always commits the incumbent, not an improved optimized plan.

Exact claim A holds; novelty vs Desaulniers / Erdelić / Dastpak remains unresolved; no service or compute advantage demonstrated.

### Implications

- **Do not** open Stage 5.2 / new RACE heuristics / neural methods.
- **Final experimental reference method:** greedy charge-to-70% (strongest simple equalized baseline), with SF-RH charge-to-70% as rolling-horizon reference.
- Document RACE-RH as a **negative research result**: charging-aware RH+DP with readiness is implementable and safe, but does not beat strong conventional discrete-target charging on Casablanca train stress.

Assess paper scope as applied optimization / simulation benchmark with honest negative method result — not a TRC-grade novel algorithm claim unless Stage 6 somehow reverses this (not expected; freeze baselines).
