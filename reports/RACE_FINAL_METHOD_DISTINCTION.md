# Method Distinction — What Could Still Be Novel

## Question

Is there a defensible EV-routing-specific technical distinction beyond applying Zhao et al. (2026) assignment-consistency ideas to another domain?

## Honest answer (pre-expanded-eval)

**Assignment-consistency certificates alone: No.**  
AC-DMTA already uses interval bids, winner-stability certificates, decision-triggered communication, delay, and packet loss. RACE-ECOM’s dominance gate and PROVED/FALLBACK labeling are not a new general principle. Empirically, PROVED count was zero on the PASS-1 pilot after roster-correct coverage.

## Candidate distinction (EV-specific)

The operational object that AC-DMTA does **not** center is:

> **Hard pickup time windows + irreversible locked EV route segments + conservative energy insertion, under delayed peer bids whose arrival can consume the same slack needed to serve.**

That yields a different decision than “communicate if the certificate fails”:

> **Commit-now vs wait:** should an EV claim with currently safe local information, or briefly wait for delayed peers, given TW slack, local travel, roster coverage, and the risk that stale peer bids veto a still-feasible local service?

Implemented as `deadline_energy_assignment_wait_s` + optional `delay_aware_trust` (ignore peer bids older than a delay-scaled trust horizon when deferring).

This is **not** a theorem transplanted from AC-DMTA. It is a coordination-deadline rule for irreversible EV commitments.

## What would count as PASS (method-centered)

The refined selective/ECOM-deadline protocol must show a **reproducible** service–communication advantage under delay vs unchanged selective **and** vs no-communication / full — or a clearly stated property with empirical support that waiting for delayed bids destroys OT while early commit preserves it.

## What would count as PARTIAL

Selective RACE-COMM remains the strong applied result (safe, large byte savings at delay 0); ECOM/certificates add little; deadline refinement helps only modestly or only in narrow cells.

## What would count as FAIL

No technical distinction beyond prior art, and no empirical improvement from the refinement.

## Post-expanded-eval update (60 scenarios)

The EV-specific distinction that **survived** is **not** ECOM certificates. It is the delay-aware commit/trust rule:

- Under delay, unmodified selective/ecom defer to stale peers and lose OT vs none.
- `deadline_energy` wait + `delay_aware_trust` drives peer defers → 0 and recovers OT to within the 2 pp noninferiority margin of none at 30/120 s, while cutting bytes vs selective.

That is a consequential coordination-deadline property for irreversible EV pickups. It is still an incremental protocol on top of selective RACE-COMM, not a new certificate theory relative to Zhao et al.

See `RACE_FINAL_PUBLICATION_DECISION.md` (**PARTIAL**).
