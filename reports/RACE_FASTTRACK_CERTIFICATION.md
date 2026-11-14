# RACE-CERT — Certification Formalism

## Decision object

For each feasible EV–task pair, the **allocation score** is travel-primary incremental routing burden `marginal_travel_s` (lower better), matching the existing `bid_sort_key`. Hard physical feasibility remains a separate gate (`check_insertion` / energy reserve). Soft keys: energy flexibility, deadline slack, vehicle id.

## Certificate

Each transmitted bid may carry a travel-cost interval `[cost_L_s, cost_U_s]`.

Construction (`coordination/certifying_protocol.py`):

| Source | Interval |
|--------|----------|
| Self, fresh insertion check | `[c, c]` (point; assumption A2) |
| Peer payload of age `Δ` | `[c−w(Δ), c+w(Δ)]` with heuristic `w(Δ)=min(180, 5+0.15Δ)` (A3) |
| Infeasible / withdrawn | `[∞, ∞]` |

## Dominance rule

Among the **represented** candidate set (self + fresh peers), vehicle `j` is **travel-certified** if
\[
U_j < \min_{i\neq j} L_i.
\]

If any announced peer lacks a fresh certificate (incomplete coverage), or intervals overlap, the view is **non-certified** and the protocol falls back to sending/requesting detailed bids (`ambiguous_fallback`).

## Conditional proposition (stated, not over-claimed)

**Under assumptions A1–A4** (see module docstring): if every eligible competitor is represented by a fresh interval and dominance holds, then `j` uniquely minimizes travel-primary cost in that set. Further detailed bids cannot overturn that ranking *without leaving their declared intervals*. Commitment still re-validates physics.

**This is not a general theorem** under arbitrary Casablanca travel-time Lipschitz constants. Aging wideners are **declared heuristics**. Label implementation: `heuristic_interval_v1`.

## Comparison to prior art

- Distinct from generic VoI / sparse MARL gates by tying intervals to **energy-feasible insertion costs** and **irreversible commitments**.
- Distinct from full distributed auctions by suppressing messages once dominance holds under the certificate.
- Must still be compared empirically to selective, full, and matched-budget random baselines (pilot).
