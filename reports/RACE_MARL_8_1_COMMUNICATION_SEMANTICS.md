# RACE-MARL Stage 8.1 — Communication semantics

## Decision schedule

Physical decision epochs are triggered by:

- Request release
- Charge end
- Bid-assign window

**Message delivery does not create a new physical decision** (`message_triggers_decision=False` by default). Delivered bids update the local inbox for the next eligible decision.

This removes the Stage 8 pathology where 30 s delay produced ~1500 send actions with zero pickups.

## Send limits

| Control | Value |
| --- | --- |
| Per-(vehicle, request) cooldown | 30 s |
| Max sends per (vehicle, request) | 2 |
| Ablation A | communication disabled |
| Ablation B | force send of top feasible task bid each epoch (op still free) |
| Ablation C | random send with matched probability |
| Ablations D/E/F | learned send/suppress on per-task comm head |

## Fairness vs full communication

Operational action space is **identical** across A–F. Full communication cannot claim an extra physical action relative to selective; it only forces the communication head.

## Delayed / missing messages

- Delayed bids cannot unlock hidden peer truth.
- Lost packets leave peer slots masked (zeros).
- Locked commitments remain immutable under late bids (simulator ownership rules unchanged).
- Cooldown + send caps bound message activity during assign windows.
