# RACE-MARL — Research decision (after Milestone 1–4)

## Milestone scores

| Milestone | Result |
| --- | --- |
| 1 Protocol repair + larger delayed pilot | **PARTIAL** — repairs landed; compact pilot; full@delay skipped |
| 2 Genuine MAPPO smoke (gradients, checkpoints) | **PASS** |
| 3 Casablanca trained policy | **PASS** (seeds 0/1, checkpoints saved) |
| 4 Full learned ablations | **PARTIAL** — A–F executed on compact matrix |

## Binding decision

**PARTIAL.** F mean_ot=0.247; no clear gain over no-comm on this compact diagnostic set. Best=B_full_comm (0.454).

Do **not** claim TRC-ready novelty until larger multi-seed held-out evaluation with uncertainty intervals.
Do **not** reintroduce RACE-RH / inverse-slack methods.

Pipeline summary: `{"milestone3": "F seeds 0/1 trained; best=seed1_best mean_ot~0.25 on diagnostic", "milestone4": "A-F ablations executed; B strongest on compact diagnostic", "decision": "PARTIAL"}`
Ablation wall: `n/a` s.
