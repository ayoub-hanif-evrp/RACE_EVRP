# FINAL NOVELTY POSITIONING

## Verified closest prior art

1. **Zhao et al. (2026)** AC-DMTA, *Drones* 10(7):523, DOI `10.3390/drones10070523` — interval bids, assignment-consistency certificates, communication suppression under stale UAV info.  
2. **Cong et al. (2026)** ET-PBBA, *Drones* 10(9):684, DOI `10.3390/drones10090684` — event-triggered path-based one-pass assignment with energy terms; centralized event-local scan, not delayed nonbinding multi-agent deferral analysis.  
3. Classical CBBA / event-triggered consensus auctions.  
4. Dynamic EVRP with TW + charging (operational domain, not automatically novel).  
5. Distributed auctions, timeouts, fallbacks.

## Comparison (compressed)

| Axis | Zhao AC-DMTA | Cong ET-PBBA | RACE-COMM CSC-lite |
|------|--------------|--------------|--------------------|
| Object | UAV bundles | UAV event-local assign | EV pickup claim + locks |
| Bid binding | Consensus winners | One-pass award | Offers nonbinding under delay |
| Energy | Interval envelopes | Path/energy score | Conservative insertion gate |
| Delay handling | Certificate silence / recency | Event activation | **Ignore delayed offer-only deferral** |
| Ownership | Distributed tables | Event assignment | Atomic registry |
| Empirics | UAV sims | UAV sims | Casablanca EV development |

## Honest classification

**Focused applied algorithmic contribution + computational/negative research finding.**

Defendable points:

1. Zero-delay selective bidding is **service-tied with full bidding** at ~75% fewer attempted bytes (development evidence).  
2. Treating delayed nonbinding offers as commitments **harms hard-TW EV service**; CSC-lite prevents that by construction and matches matched-wait zero-comm.  
3. Confirmation signalling and peer-energy message fields did **not** add operational value here.

**Not** a strong TR Part C “new theory” claim solely on CSC naming. Venue should follow evidence weight after locked_final.

## Contribution split for the paper

- **A** Immediate multi-agent bidding value (ownership changes @0; modest mean OT lift, CI includes 0 on n=60).  
- **B** Communication efficiency vs full.  
- **C** Safe fallback under delay (negative finding about speculative deferral).  
- **D** Battery-safe online execution (established conservative insertion + charging — supporting, not the novelty core).
