# RACE-MARL Stage 8.1 — Correctness audit

**Starting commit:** `ad06455` (Stage 8 historical).  
**Scope:** Repair scientific MARL formulation before any large training campaign.

## Defects identified (pre-repair)

| # | Defect | Location | Severity |
| --- | --- | --- | --- |
| 1 | SEND competed with CLAIM in one discrete action | `env.py` | Critical |
| 2 | Obs used only `len(peer_bids)`, not bid contents | `env.py` `_encode` | Critical |
| 3 | Flattened agent×time GAE (EV1_t → EV2_t as time) | `buffer.py` / `mappo.py` | Critical |
| 4 | Cumulative `n_bid_messages` re-penalized | `env.py` `step` | High |
| 5 | MESSAGE_DELIVER triggered unbounded decision loops | `env.py` `_advance_to_decision` | Critical |
| 6 | Train checkpoint selection reused train factory | training scripts | Medium |

## Repairs implemented

1. **Factorized actions:** `(operational, communication)` with independent masks/heads.
2. **Peer-bid features:** per-task best competing travel/energy/slack/age/validity/count + pending window.
3. **Time-indexed `FleetRolloutBuffer`:** GAE along TIME only; team advantage broadcast to agents.
4. **Incremental rewards:** Δ on-time + small Δ served − `msg_cost` × Δ messages; no terminal OT double-count.
5. **Message info-only default:** deliveries update inbox without creating extra decision epochs; send cooldown + per-task send cap.
6. **Validation factory** for checkpoint selection; procedural jitter on train-only request subsets.

## Gate 1 tests

| Test file | Purpose |
| --- | --- |
| `tests/test_marl_time_axis_and_gae.py` | Independent GAE numerics; same-time agents ≠ extra discount |
| `tests/test_marl_factorized_actions.py` | Claim+send same epoch; no-comm masks |
| `tests/test_marl_reward_accounting.py` | Incremental message cost; OT counted once |
| `tests/test_marl_peer_bid_features.py` | Peer payload changes obs |
| `tests/test_marl_delayed_communication.py` | Finite sends under 30 s delay |
| `tests/test_marl_training_generalization.py` | BC + MAPPO smoke |

**Gate 1 status:** PASS (pytest suite green).

## Historical Stage 8 results

`marl_ablations_*.csv` and Stage 8 checkpoints remain in-repo as **historical**. They are **not** valid for final method comparisons after this formulation change.
