# FINAL COMMUNICATION RESULTS (Prompt 3)

Primary cost metric: **`n_bid_attempted_bytes`** (serialized payload × recipient fan-out, including network drops).

## Zero-delay means (locked_final, n=30)

| Treatment | Attempted bytes | Delivered bytes | Notes |
|---|---:|---:|---|
| A_NONE_NOW | 0 | 0 | No messages |
| B_FULL_COMM | 231 264 | 231 264 | Full bidding |
| C_PERIODIC_COMM | 48 864 | 48 864 | 300 s task-bid refresh (corrected) |
| D_RANDOM_BYTE_MATCHED | 49 030 | 49 030 | Actual-payload budget (corrected) |
| E_EVENT_TRIGGERED | 55 306 | 55 306 | Same bytes as selective family |
| F / G / H | 55 306 | 55 306 | Identical selective traffic @0 |
| I | 0 | 0 | Wait matched; no messages |
| J | 50 732 | 50 732 | Placebo messages; unused for claims |

## Delayed means

| Treatment | 30 s attempted / delivered | 120 s attempted / delivered |
|---|---|---|
| B | 341 491 / 21 487 | 253 865 / 18 197 |
| F | 313 399 / 40 757 | 154 548 / 27 015 |
| G | 308 077 / 35 925 | 48 903 / 11 660 |
| H | 64 434 / 16 450 | 48 903 / 11 660 |
| J | 64 434 / 16 450 | 48 903 / 11 660 |
| I / A | 0 / 0 | 0 / 0 |

At positive delay, delivery ≪ attempts because of delay windows and supersession; attempted bytes remain the declared primary cost.

## Comparator validity

- Random locked ratio vs H @0: 49 030 / 55 306 ≈ **0.887** (training calibration 0.898).
- Periodic locked traffic is **positive** and nontrivial (~49 kB), fixing Prompt 2’s zero-byte defect.
- Periodic comparator uses **task bids**, not generic state snapshots (`periodic_state_broadcast=False`).
- J demonstrates that matched message volume without claim use equals I on service.

## Accounting fields recorded per run

Attempted / dropped / scheduled / delivered message counts and bytes; superseded and coalesced delivery events where instrumented. No state-broadcast traffic is mixed into task-bid totals for the primary periodic comparator.
