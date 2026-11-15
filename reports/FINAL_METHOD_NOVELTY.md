# FINAL METHOD NOVELTY

## Closest verified prior art

### Zhao et al. (2026) — AC-DMTA

- **Citation:** Chenxu Zhao, Meixuan Li, Xianqiang Zhu, Cheng Zhu. *Assignment-Consistent Dynamic Multi-UAV Task Allocation*. *Drones* 2026, 10(7), 523. DOI `10.3390/drones10070523`.
- **Object:** Multi-UAV CBBA-style bundles; interval bids; communicate when certificates may flip winners.
- **Bids:** Point → interval under stale uncertainty; assignment-consistency certificates suppress irrelevant traffic.
- **Binding?** Local winner tables / consensus — not EV hard route locks + central registry.
- **Overlap with RACE:** stale/asymmetric info, delay/loss evaluation, decision-triggered messaging.
- **Non-overlap:** AC-DMTA does not study **speculative deferral to nonbinding cost offers** that destroy hard-TW EV service; RACE-ECOM-style PROVED certificates were already rejected as non-contributing empirically.

### Distributed auctions / CBBA lineage

ED-CBBA, CBBA-ETC, classical CBBA: consensus on bundles; event triggers; generally treat a better bid as assignment-relevant evidence. Timeouts exist, but the EV-specific failure (defer → peer never claims → miss TW) is not their primary theorem.

### Online VRP commitment / EV routing

Irreversible in-progress legs, charging, conservative energy insertion under hard pickups are domain mechanisms present in RACE’s simulator; **application alone ≠ novelty**.

## Comparison matrix (compressed)

| Axis | AC-DMTA | Classic auction+timeout | RACE-COMM Selective + CSC-lite |
|------|---------|-------------------------|--------------------------------|
| Decision object | Bundle winners | Task winners | EV pickup claim + locked route |
| Peer bid meaning | Interval cost / reward | Cost/score | Feasible **offer** (nonbinding) |
| Binding offers? | Consensus winner | Usually treated as ranking truth | **No** under delay |
| Ownership | Distributed tables | Auction award | **Atomic registry** |
| Ack required? | Certificate silence | Optional | **No** (frozen); optional intent unused |
| Missing/obsolete | Recency / envelopes | TTL | TTL + commitment_version from inbox |
| Wait/timeout | Guarded retries | Deadline heuristics | `deadline_energy` finite wait |
| Energy + charge | Envelope | Varies | Conservative insertion + depot charge |
| Irreversible commits | Path-version repair | Soft | Locked prefix immutable |
| Math properties | Local sufficient certificates | Heuristic | Registry exclusivity + tested invariants |
| Comm cost | Certificate-driven ↓ | Varies | Selective; no confirm traffic |
| Evidence | UAV sims | Mixed | 6-sc EV pilot; delay null vs no-peer |

## What remains defensibly distinct

1. **Explicit offer ≠ intention ≠ ownership ≠ service** in an EV fleet with hard TWs, locked legs, and a registry — and a claim rule that **refuses delayed offer-only deferral**.
2. Empirical demonstration that treating delayed offers as ranking truth **causes large OT losses**, while CSC-lite restores the matched no-peer service schedule **without** needing acknowledgement rounds.
3. Honest null: under delay, multi-agent ranking contribution is **zero** once offers are non-credible — a publishable negative/coordination finding, not a fake cooperative win.

## What is **not** claimed novel

- Naming “RACE-CSC”.
- Claim/ack handshakes in general.
- Selective event-triggered bidding alone (overlaps CBBA-ETC / prior RACE-COMM).
- Interval winner certificates (Zhao / rejected ECOM).
