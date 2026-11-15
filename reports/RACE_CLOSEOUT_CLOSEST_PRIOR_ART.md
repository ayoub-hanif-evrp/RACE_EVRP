# Closest Prior Art — Closeout Audit

**Primary reference:** Zhao et al. (2026), *Assignment-Consistent Dynamic Multi-UAV Task Allocation*, *Drones*, DOI `10.3390/drones10070523`.

## Already known (do not claim as RACE novelty)

| Element | AC-DMTA (Zhao 2026) |
|---------|---------------------|
| Decision-relevant selective communication | Yes — communicate when stale info may change assignment |
| Interval-valued bids | Yes — envelopes over age / motion / energy / status |
| Assignment-consistency / winner-stability certificates | Yes — local sufficient conditions |
| Energy and timing constraints | Yes — UAV energy + deadlines in feasibility |
| Stale / asymmetric information | Yes — core setting |
| Asynchronous deconfliction | Yes — recency / path-version fusion |
| Delayed and lossy links | Yes — evaluated with guard-interval retries |

Secondary overlap: 2026 event-triggered adaptive consensus (CBBA-ETC) — significant-bid / conflict / adaptive-time triggers without interval certificates.

**Generic interval dominance, event-triggered messaging, and battery-aware auctions are not novel.**

## Formal comparison to RACE-ECOM

| Axis | Zhao AC-DMTA | RACE-ECOM (PASS 1) |
|------|--------------|--------------------|
| Decision object | CBBA-style bundles + winner tables | Single-item online pickup claims + atomic registry |
| Intervals | Model-based envelopes with local soundness claims | Heuristic travel wideners; **not** theorems |
| Empirics | Certificate-driven silence is the method | PROVED ≈ 0 after roster-correct coverage |
| Domain | Multi-UAV | Ground EV fleet on time-dependent city graph |

Transplanting AC-DMTA to EVs **without a new decision mechanism** is not a methodological contribution.

## Where an EV-specific mechanism *can* differ

Only if it changes decisions through:

1. Depot charging / energy restoration coupled to online insertion.
2. Conservative insertion feasibility with irreversible locked travel/service.
3. Hard pickup completion deadlines vs communication wait.
4. **Deadline-safe assignment timing:** commit now vs wait for delayed peers without treating silence as peer infeasibility.

Item (4) is the mechanism tested in this closeout (not certificate dominance).

## Verdict

Assignment-consistency certificates as in RACE-ECOM are **insufficiently distinct** from Zhao et al.  
A defensible distinction, if any, must be the **communication-aware, deadline-safe assignment timing** rule under irreversible EV commitments — judged empirically against selective bidding on the 60-scenario development ensemble.
