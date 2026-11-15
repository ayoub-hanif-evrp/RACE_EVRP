# Closeout Method Formulation — Deadline-Safe Assignment Timing

## Fixed operational core

Native cooperative routing · charge-to-70% readiness · conservative insertion feasibility · atomic ownership · irreversible locked commitments. **No new neural router.**

## Decision of interest

After a request release and local bid exchange:

**A. Immediate safe commitment** — claim now with currently feasible local insertion.  
**B. Bounded wait** — wait at most for peer bids that can still arrive before the commitment becomes infeasible.  
**C. Safe fallback** — when the communication/assign deadline expires, assign using trusted information only.

Missing peers are **unknown**, never assumed infeasible.

## Waiting rule (`deadline_energy_assignment_wait_s`)

Inputs: TW slack, message delay, roster competitors, fresh peer bid count, optional local travel.

Return **0** (immediate) when:

- `comm_mode ∈ {none, periodic}` (no delayed peer bids expected on the exchange path) — **causal fix**;
- delay = 0;
- slack ≤ urgency buffer;
- delay ≥ `delay_slack_frac × slack` (waiting would burn the TW);
- local travel + urgency ≥ slack;
- roster competitors = 0 or peer coverage already complete.

Otherwise wait `min(delay, useful_slack, max_wait)` — **never** `1.25×delay` for non-communicating policies.

## Stale-peer trust (`delay_aware_trust`)

When claiming, ignore peer bids older than `max(15, 0.5×message_delay)`. Prevents deferral to delayed certificates that veto a still-feasible local service.

## Fair physical decision opportunities

`fair_physical_decisions=True` (default):

- **Physical claim/charge reasons:** `bid_assign`, `vehicle_idle`, `charge_end`, `service_end`, `pickup_missed`, `epoch`.
- **Info-only:** `message`, `periodic_broadcast`, `bid_exchange` — may transmit/ingest bids; **must not** claim or start charging.

Separates communication delay / messaging from assignment opportunity counts.

## Primary tested protocol

**H — selective_deadline:** selective messaging + deadline-energy wait + delay-aware trust.

Comparators: none, full, periodic, byte-matched random, **event_triggered** (first feasible + material/invalidation only), selective, ecom, centralized greedy (full info reference).

## Conditional property (not oversold)

**Proposition (conditional deadline feasibility of commit-now).**  
If a vehicle has a currently feasible insertion under the conservative checker, and the assign wait is set to 0 whenever `delay ≥ α·slack` or local travel exhausts slack, then the policy does not *intentionally* postpone a feasible claim past the modeled feasibility horizon induced by that wait. Physics is still re-checked at claim time. This is a **design invariant**, not a global optimality theorem.

## Complexity

Per decision: same as selective — \(O(R·P)\) bid compares; wait is \(O(1)\).
