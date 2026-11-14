# RACE — Certificate Validity Statement (PASS 1)

## Verdict

Age-widened cost intervals are **heuristic / conditional**. They are **not** mathematical safety certificates for Casablanca time-dependent travel unless stronger Lipschitz/travel-time bounds are proved (they are not).

Incomplete public-roster coverage **blocks** PROVED status. Silent competitors are **unknown**, not assumed infeasible.

## Assumptions (A1–A4)

Copied from `certifying_protocol.py`:

1. Ranking key = `marginal_travel_s` (energy/slack soft ties only).
2. Self cost from fresh `check_insertion` is a point interval \([c,c]\) under current commitments.
3. Peer age \(\Delta\) widens by \(w(\Delta)=\min(180,5+0.15\Delta)\) seconds — **declared heuristic**.
4. Certification only among represented candidates; missing roster members ⇒ non-certified.

## Correctness gates (tests)

| Test | Result |
|------|--------|
| `fleet_vehicle_ids` on restricted obs (empty peers ≠ empty fleet) | PASS |
| Silent best competitor ⇒ `incomplete_peer_coverage`, not certified | PASS |
| ECOM initial under incomplete coverage = FALLBACK/HEURISTIC, not PROVED | PASS |
| Delayed full completes without queue blowup | PASS |
| Matched budget charges recipient fanout | PASS |

Source: `tests/test_race_ecom_pass1.py`, `tests/test_race_cert_protocol.py` (13+ tests green in PASS 1 run).

## Labeling discipline

| Status | When used |
|--------|-----------|
| A PROVED | Complete coverage + interval dominance |
| B HEURISTIC | Incomplete / aged / ambiguous |
| C FALLBACK | Safe bid without cert claim |

Execution always re-validates energy, windows, and locked commitments before ownership.

## What failed previously (fixed)

- Using `len(obs.peers)` as competitor count → false certification when state table empty.
- Treating heuristic wideners as safety theorems in narrative.

## Residual risk

Heuristic \(w(\Delta)\) can be too tight or too loose under congestion spikes. PASS 1 reports PROVED rates transparently; PASS 2 must not claim non-heuristic safety.

## Pilot empirical rate

On the 6-scenario delay-0 pilot, mean `n_ecom_proved` = **0** and mean `n_ecom_fallback` ≈ **65**. After roster-correct incomplete-coverage checks, interval dominance almost never yields status A on this set. That is a validity success (no false PROVED), not an empirical certification payoff.
