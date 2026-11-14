# RACE-ECOM — Novelty Assessment (PASS 1)

Literature reviewed through early 2026 (arXiv / TR-C / IEEE / AURO-class MRTA). Honest positioning for Transportation Research Part C.

## Closest prior art

| Work | Info / Comm | Safety | Commitments | Gap vs RACE |
|------|-------------|--------|-------------|-------------|
| ED-CBBA (arXiv:2509.06481, 2025) | Event-triggered CBBA; ≤52% fewer msgs; conflict-free consensus | Mission consensus, not EV energy | Bundle consensus | No EV SOC/hard windows/irreversible pickup locks; not delayed urban logistics |
| Otte et al. AURO 2019 / MRS 2017 | Auctions under lossy links; performance degradation analysis | Allocation quality bounds | Auction rounds | No energy-feasible EV insertion; no public-roster incomplete-coverage certificates |
| CBBA / ACBBA (Choi et al.; Johnson et al.) | Decentralized consensus auctions | 50% optimality-style guarantees | Conflict-free bundles | Assumes richer consensus messaging; not energy-safe online pickup with locked routes |
| EV-DPDPTW rolling horizon (COOPIS-style) | Central/cooperative fleet ops | Recharge heuristics | Dynamic PDPTW | Communication not the method; typically more global info |
| TR-C 2024 EV PDP + queues (Zhou et al.) | Optimization / queues | Energy + TW | Planning-centric | Not peer-message certification under delayed info |
| Agent consensus EV PDP (Appl. Sci. 2024) | Negotiation vs closest | Battery costs | Soft/agent negotiation | No certified incomplete-coverage discipline; not byte-matched fair ablations |
| Auction + energy AMR (arXiv:2603.21545, 2026) | Sequential auction + event reschedule | Battery model | Factory AMR | Different domain; central auction stages; not delayed peer certificates for irreversible pickups |
| Value-of-information / event-triggered control | Send when estimate error large | Control-theoretic | Continuous plants | Not EV task auctions with roster coverage |

## What is **not** novel

- Dominance \(U_j < \min_i L_i\).
- Selective / material-change event triggers (RACE-COMM selective already).
- Native cooperative insertion routing (strong but previously established in this repo).
- Claiming heuristic age wideners as proved travel-time certificates.

## Defensible RACE distinction (candidate)

**Energy-feasible online EV pickup with irreversible commitments, hard deadlines, delayed/lossy peer bids, atomic ownership, and decision-critical messaging that refuses PROVED status under incomplete public-roster coverage — with fair communication baselines and causal multi-agent tests.**

The methodological kernel is the **coverage-aware certificate discipline + decision-critical gate (ECOM)** on top of a frozen physically gated controller — not a new neural router.

Whether this is enough for TR Part C depends on PASS 1/2 evidence that ECOM improves the service–bandwidth frontier **beyond selective**, or that the certified incomplete-information theory + fair delayed-communication evaluation is itself the contribution even if ECOM ≈ selective on OT.

## Competing risk (honest)

If pilot shows G≈E on OT and bytes, novelty rests on:

1. Correct certification semantics (roster / unknown competitors).
2. Fair delayed-full and matched-random methodology.
3. Explicit A/B/C labeling + conditional proposition.

That can still be a solid methods paper, but **not** a “new protocol beats selective” claim.

## GO implication

See `RACE_FINAL_GO_NO_GO.md` after pilot numbers.
