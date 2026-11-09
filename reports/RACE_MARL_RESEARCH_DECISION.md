# RACE-MARL — Research decision (after Milestone 1–2)

## Milestone scores

| Milestone | Result |
| --- | --- |
| 1 Protocol repair + larger delayed pilot | **PARTIAL** — repairs landed; compact pilot shows selective≈full at delay 0, weaker under 30 s delay |
| 2 Genuine MAPPO smoke (gradients, checkpoints) | **PASS** (`marl_checkpoints/smoke.pt`, params changed) |
| 3 Casablanca trained policy | **NOT STARTED** |
| 4 Full learned ablations | **NOT STARTED** |

## Binding decision

**Continue.** The repository now contains:

1. Scientifically corrected non-learning RACE-COMM protocol.
2. A **real** MAPPO CTDE stack with proven parameter updates (not a renamed heuristic).

**Do not claim** a TRC-ready MARL contribution until Milestone 3–4 produce held-out Casablanca results with fair communication ablations.

**Do not** reintroduce RACE-RH / inverse-slack methods.

Next work: train on Casablanca procedural episodes, then freeze checkpoints for matched communication ablations.
