# RACE-MARL Stage 8.3 — Event Parity

## Native vs MARL decision triggers

| Event / reason | Native (`OnlineSimulator.run` + `_maybe_decide`) | MARL wrapper before 8.3 | MARL wrapper after 8.3 |
|----------------|--------------------------------------------------|-------------------------|------------------------|
| `request_release` | Yes | Yes (return) | Yes |
| `service_end` | Yes (then `_start_next_leg`) | Physics only; **no agent return** | Yes; autoleg deferred until after step |
| `vehicle_idle` (depot arrival / post-arrival idle) | Yes | Physics only; **no agent return** | Yes when vehicle idle after arrival |
| `charge_end` | Yes | Yes | Yes (autoleg deferred) |
| `bid_assign` | Yes | Yes | Yes |
| `pickup_missed` | Yes | Via `_on_arrival` miss path; no return | Idle return when applicable |
| `message` | Yes (optional) | Info-only by default | Info-only by default (unchanged) |
| `periodic_broadcast` / `epoch` | Optional | Not used | Not used |
| `shift_end` | Expire opens | Expire opens | Expire opens |

## Root cause addressed

Stage 8.2 MARL `_advance_to_decision()` executed `SERVICE_END` / idle arrivals without returning control. An EV could finish a pickup with other AVAILABLE requests waiting and not reconsider until the next release — unlike `RaceCooperativePolicy`.

## Implementation

1. Suppress `_start_next_leg` during event handlers; record `_pending_autoleg`.
2. Return a decision when the vehicle is idle after service/arrival/charge.
3. After MARL claims/charges, `_flush_autoleg()` starts next legs (native post-decide order).

Counters: `n_decision_service_end`, `n_decision_vehicle_idle`, `n_decision_charge_end`, `n_decision_release`.

Tests: `tests/test_marl_event_parity.py`.

## Residual factorized gap

Native `_maybe_decide` is **two-phase** on `request_release` (`bid_exchange` → flush → `bid_assign`) and applies claims **sequentially** across vehicles. MARL `step` now flushes zero-delay bids before batched claims, but still resolves ownership in one batched round. Native-bridge **execute** (sequential mutate) ≈ 0.82 OT; factorized **intent→step** ≈ 0.60 mean — remaining ~20pp is interface/scheduling, not missing `service_end` returns.
