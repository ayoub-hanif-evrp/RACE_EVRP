# Stage 4A — Experiment results (pilot)

**Config:** `data/casablanca/online_results/stage4a_experiment_config.json`  
**Metrics:** `stage4a_pilot_metrics.csv`  
**Budget:** \(K=2\) synthetic continuations, ≤3 synthetic requests, horizon \(H=2400\) s, ≤6 claim candidates, ≤2 charge candidates.  
Stage 3C FAIL for inverse-slack RACE is unchanged.

## Toy / unit tests

`tests/test_stage4a_postdecision.py` — anti-leakage strip of unreleased eval requests; early-charge and ample-battery smoke paths; ablation without future eval.

## Casablanca pilot (executed)

### Peak stress seed2

| Policy | Full SOC served | SOC 35% served | Charges (35%) | Lookahead s (35%) |
| --- | ---: | ---: | ---: | ---: |
| Greedy + adaptive | 37 | 29 | 3 | 0 |
| Greedy + always-on | 36 | **33** | 8 | 0 |
| Service-first RH | 37 | 28 | 3 | 0 |
| Postdecision no-future | 37 | 26 | 3 | 0 |
| One-step rollout (claim-only + adaptive) | **38** | 29 | 3 | 27.8 |
| RACE postdecision (joint charge) | 37 | 29 | 4 | 27.1 |
| Postdecision no-charge actions | 37 | 18 | 0 | 9.8 |

### Baseline seed1

All primary methods serve 10/12 at full and 35% SOC (race_pd_no_charge drops to 9/12 at 35%).

### Tight windows seed3

Greedy adaptive 26/30 (full) and 21/30 (35%); RACE postdecision matches 21/30 at 35% with more energy/charges; always-on **hurts** (18/30).

## Interpretation

1. **Charging rule still dominates low-SOC peak service** (always-on 33 > adaptive/postdecision 29).
2. After fixing single-claim bugs, postdecision ≈ adaptive greedy; **no consistent service gain**.
3. Conventional one-step rollout once beats greedy by +1 on peak full SOC; RACE-with-charge does not improve further.
4. Removing endogenous charge candidates collapses low-SOC peak service to 18 — confirms charging coupling matters, but reactive always-on already captures more value without MC lookahead.
5. Lookahead adds ~20–30 s CPU per stress episode at this budget — online-feasible for the pilot, not justified by service gains.

No statistical significance claimed.
