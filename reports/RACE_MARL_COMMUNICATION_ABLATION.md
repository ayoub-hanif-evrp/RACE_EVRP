# RACE-MARL — Communication ablation status

## Non-learning protocol repairs (Milestone 1)

Completed in code:

- Async bid assign windows (`BID_ASSIGN_WINDOW`) with deadline-aware waits.
- Selective expiry uses **last transmitted** bid expiry.
- Commitment-version / seq supersession; withdrawals after new claims.
- Periodic mode can disable generic state floods (`periodic_state_broadcast=False`).
- Matched-budget random control (`random_matched`).
- Packet-loss stream.
- Honest documentation: ranking is travel-primary; `charge_burden_s` not used in ranking.

Pilot runners: `scripts/run_race_comm_pilot_v2_compact.py` (and full `run_race_comm_pilot_v2.py`).  
Results: `data/casablanca/online_results/race_comm_pilot_v2.csv`.

### Compact pilot means (6 scenarios, SOC35)

| Delay | Mode | Mean OT | Mean msgs | Mean CF changes |
| --- | --- | ---: | ---: | ---: |
| 0 s | none | ~0.77 | 0 | 0 |
| 0 s | selective | ~0.80 | ~70 | >0 |
| 0 s | full | ~0.80 | much higher | matches selective CF |
| 0 s | random_matched | lower / mixed | ≈ selective budget | weak CF |
| 30 s | none | lower | 0 | 0 |
| 30 s | selective | often ≥ none | moderate | CF often 0 (bids late) |

**Interpretation:** zero-delay selective still helps; under 30 s delay, benefit shrinks and CF claim-changes often vanish — async robustness remains open for MARL.

## Learned communication ablations (Milestone 4)

**Not yet executed** at Casablanca scale. Smoke MAPPO proves training mechanics only.
