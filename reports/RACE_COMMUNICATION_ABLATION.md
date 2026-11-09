# RACE-COMM — Communication ablation pilot (Phase 4 milestone)

**Runner:** `scripts/run_race_comm_pilot.py`  
**Results:** `data/casablanca/online_results/race_comm_pilot.csv`, `race_comm_pilot_summary.json`  
**Design:** identical cooperative bid-ranking assignment; only messaging mode changes.  
**Scenarios (pilot):** release peak2, tight3; eval peaks 1201–1202. Suites: SOC35 + full SOC.  
**External reference:** full-info greedy→70%.

## SOC35 mean on-time (n=4 scenarios)

| Mode | Mean OT | Mean policy msgs | Mean CF claim changes |
| --- | ---: | ---: | ---: |
| none | 0.783 | 0 | 0 |
| random | 0.790 | 99.5 | 1.75 |
| periodic | 0.808 | 240.3 | 0 |
| full | **0.810** | 336.0 | **11.25** |
| selective | **0.810** | **72.0** | **11.25** |

Paired Δ vs none: selective/full **+0.027**; random **+0.006**; periodic **+0.025** (but CF changes = 0 — periodic mostly state spam / timing, not bid-driven ranking).

## Interpretation

1. **Communication can change decisions** under the new energy-certified bidding rule (CF changes > 0 for full/selective).
2. **Selective ≈ full service** at ~**4.7× fewer** voluntary policy messages on this pilot.
3. **Random matched-ish budget does not** reproduce selective’s CF effect → message *selection* matters.
4. Pilot scale is small (n=4). This is a **go signal for larger Phase 5 evaluation**, not a publication-ready CI.

## Failures / caveats

- Tight-windows seed3: selective/full beat `none` but remain below full-info greedy→70% (0.70).
- Zero message delay used so same-tick bid rounds are meaningful; delayed-message robustness is Phase 5.
- Hybrid registry architecture remains (not fully decentralized).
