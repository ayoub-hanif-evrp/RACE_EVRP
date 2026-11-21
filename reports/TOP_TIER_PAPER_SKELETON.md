# Top-Tier RACE-MARL — Paper Skeleton (Phase 5)

**Status:** numbers filled — see `reports/TOP_TIER_RESULTS.md`.  
**Do not retune** after reading `phase5/locked_final_g6.json`.

## Working title

Multi-agent RL for online electric pickup fleets under selective communication, delay, and nonlinear charging.

## Claim

Learned selective + energy-certified communication (F) matches full-comm service on conflict stress at substantially lower bytes, recovers communication value under delay via assign-wait, and nonlinear partial charging beats always-full on energy-binding tiers.

## Method (1 paragraph)

CTDE MAPPO over a native-parity MARL env (sequential claims, bid-exchange → assign-wait → bid_assign under delay). Warm-start BC/DAgger from `RaceCooperativePolicy`, then freeze-op fine-tune of the communication head. F uses open send masks with execute-time cert filters (best-travel opener, contested cap-2, fleet ≤2 certs/request).

## Main results to cite (dev / Phase 4)

| Result | Where |
|--------|--------|
| G4 multi-seed conflict delay0 nv3 | `phase3_g4_multiseed.json` — hard 3/3 |
| Energy-binding G4 | `phase4/conflict_energy_g4.json` — hard 6/6 |
| Delay=30 G3/G4 | `phase4/delay30_g3_g4.json` — hard 2/3 |
| Fleet nv 3/5/8 | `phase4/matrix_fleet.json` — hard 3/3 @3&5; nv8 ceiling |
| G5 NL partial vs full | `phase4/g5_nl_charge.json` — hard 2/3 + exact C |
| CIs package | `phase4/phase4_summary.json` |
| **Locked holdout (G6)** | `phase5/locked_final_g6.json` |

## Ablations

A no-comm · B full · C random matched · F RACE-MARL (hero). Optional later: D/E, native selective reference.

## Figures

Generated under `reports/figures/top_tier/` (regen: `python scripts/plot_top_tier_figures.py`).

1. `fig1_conflict_ot_bytes` — Conflict A/B/C/F OT + bytes.  
2. `fig2_delay_g3` — Delay 0 vs 30 A/B/F.  
3. `fig3_fleet_ot_bytes` — Fleet-size OT / bytes.  
4. `fig4_g5_nl_charge` — NL taper + binding partial vs full.  
5. `fig5_locked_regimes` — Locked regime + overall OT.

## Honesty notes

- Training uses synthetic geographically grounded episodes; not observed courier orders.  
- `locked_final` never used for train/tune.  
- nv=8 conflict is an easy-fleet ceiling, not a G4 failure mode.
