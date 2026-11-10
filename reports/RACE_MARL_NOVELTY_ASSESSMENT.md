# RACE-MARL — Novelty assessment (honest)

## Not novel by themselves

MAPPO (Yu et al., 2022); TarMAC-style messaging; EVRP+MARL hybrids; bidding; event triggers.

## Candidate distinction

Learned decision-relevant exchange of conservative energy-feasible task bids under delayed information and immutable online commitments, with a hard safety shield outside the network.

## Current evidence level

| Claim | Status |
| --- | --- |
| Non-learning selective can match full bidding with fewer messages (pilot) | Promising, small-n |
| Genuine MAPPO training exists in-repo | **Yes** (smoke + Casablanca) |
| Learned selective communication beats matched random / full at scale | **Measured on compact diagnostic only — see ablation CSV** |
| TRC-ready novelty | **Not yet** |

Decision: **PARTIAL**. F mean_ot=0.247; no clear gain over no-comm on this compact diagnostic set. Best=B_full_comm (0.454).
