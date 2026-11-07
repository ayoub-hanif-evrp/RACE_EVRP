# Stage 3A — Communication experiment

Executable: `scripts/run_stage3a_communication.py`  
Artifacts: `data/casablanca/online_results/stage3a_communication_metrics.*`  
Dispatch rule: identical `restricted_claim_pass` for none / periodic / decision-triggered.

Full-info greedy/RH are **references**, not message-value estimates.

## Metric integrity

| Experiment | Served | Claims |
| --- | ---: | ---: |
| baseline full greedy | 10 | **10** (was 20 before fix) |

## Peak stress (40 requests, SOC=1, δ=0, delay=60s)

| Mode | Served | Messages | Energy (kWh) |
| --- | ---: | ---: | ---: |
| Comm none | 35 | 0 | 53.37 |
| Periodic (300s clock) | **36** | 576 | 60.59 |
| Decision-triggered | 35 | 272 | 58.74 |
| Full greedy reference | 38 | 0 | 55.56 |
| Full RH reference | 38 | 0 | 49.32 |

Periodic gains **+1** served vs no-comm at large message cost; still **−2** vs full info. Triggered matches no-comm serve rate with fewer messages than periodic.

## Baseline seed1 (12 requests)

All three restricted modes: **10/12**. Triggered uses 4 messages vs 576 periodic — same serve rate, less overhead.

## Peak stress, SOC=0.35 (energy-active)

| Mode | Served | Messages |
| --- | ---: | ---: |
| None | **18** | 0 |
| Periodic | 15 | 576 |
| Triggered | 17 | 302 |

Under low SOC, this communication heuristic **does not improve** service; periodic is worst. Energy risk dominates; extra messaging does not help the shared restricted rule.

## Interpretation

1. Holding the dispatch rule fixed, communication is **not** the main driver of the prior 38 vs 35 gap (that gap remains vs full-info algorithms).
2. Periodic messaging yields a small +1 on one stress seed at high cost; not robust under low SOC.
3. Decision-triggered messaging reduces volume vs periodic but does not beat no-comm on serve rate here.

**Negative finding preserved:** decision-relevant communication is not yet justified as the primary RACE novelty on these paired runs.
