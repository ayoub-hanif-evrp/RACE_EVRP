# Trust Horizon Audit — H_CURRENT Rejects Delayed Peer Bids

**Baseline:** `e221243` H (deadline-safe selective with `delay_aware_trust`).  
**Tests:** `tests/test_trust_horizon.py`.

## Mechanism

| Quantity | Value under delay \(d\) |
|----------|-------------------------|
| Delivery time | `send_s + d` ([messaging.py](../src/race_casablanca/coordination/messaging.py)) |
| Bid age at decision | \(\ge d\) (from `as_of_s` at send) |
| Historical trust (`delay_half`) | `age ≤ max(15, 0.5d)` |

| \(d\) | Max trusted age | Age on delivery | Result |
|------:|----------------:|----------------:|--------|
| 30 | 15 | ≥30 | **Reject** |
| 120 | 60 | ≥120 | **Reject** |

Therefore **every normally delivered peer bid fails** `peer_bid_trustworthy(..., peer_trust_mode="delay_half")` at 30s and 120s.

## Empirical consistency

Closeout H: `n_defers_to_peer = 0` at both delays; physical claim counts ≈ none. Unit test `test_h_current_zero_defers_under_delay_30` reproduces zero defers.

## Claim implication

H_CURRENT’s delay-regime OT gains are **not** evidence of using delayed peer information. They are consistent with **ignoring peers** (plus shorter waits than legacy selective).

## Repair (this commit)

| Mode | Rule |
|------|------|
| `delay_half` | Broken historical filter (ablation only) |
| `ttl` / `ttl_commitment` | Transport latency alone does not void; require TTL + not withdrawn; commitment version check for `ttl_commitment` |

Physics at `check_insertion` remains absolute.
