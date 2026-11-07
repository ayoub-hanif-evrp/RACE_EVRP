# Stage 3C — Mechanism ablation (2×2)

All variants share adaptive charging, conservative feasibility, earliest-deadline task order, and marginal insertion evaluation.

| ID | Flexibility pricing | Reassignment |
| --- | --- | --- |
| A | off | off (= charge-enabled marginal greedy) |
| B | inverse-slack on | off |
| C | off | on |
| D | on | on (full RACE) |
| fixed_weight | constant \(\mu_E,\mu_T\) | off |

Raw rows: `data/casablanca/online_results/stage3c_race_metrics.csv` (136 runs). Decision traces: `stage3c_decision_traces.json`.

## Answers

### 1. Does pricing independently change assignment/position?

**Yes.** `n_flex_differing_decisions` > 0 whenever B/D/fixed_weight diverge from min-marginal travel (e.g. peak_stress_seed2 full SOC: B/D = 4 differing decisions).

### 2. Does reassignment independently improve outcomes?

**Inconsistent.** Example peak_stress_seed2 SOC 35%: C matches A on service (29) with lower energy but 20 reassignments; peak_stress_seed5 SOC 35%: C **hurts** (26 vs 27). Not a reliable standalone lever.

### 3. Do pricing and reassignment interact beneficially?

**Not systematically.** Under peak_stress_seed2 + δ=0.2, **B alone is best** (29/40) while D falls to 27. Coupling reassignment often undoes pricing gains.

### 4. Does any improvement remain after charging is equalized?

**Small and inconsistent vs greedy/A; rarely beats RH.**

| Case (adaptive) | Greedy/A | RH | B | D |
| --- | ---: | ---: | ---: | ---: |
| peak2 full SOC | 37 | **38** | 36 | 36 |
| peak2 SOC 35% | 29 | **30** | 28 | **30** |
| peak2 SOC 35% δ=0.2 | 25 | 28 | **29** | 27 |
| peak5 SOC 35% | 27 | 26 | 27 | **29** |
| tight3 full SOC | **26** | 24 | 25 | 25 |

### 5. Worth the computation?

Pricing evaluates all \((v,p)\); decision times remain online-feasible but **service/energy gains do not justify** the mechanism as a TRC contribution over charge-enabled marginal greedy + RH.

## Fixed-weight reference

Fixed weights sometimes match B’s energy reductions but do not dominate inverse-slack; neither establishes novelty over scarcity heuristics.
