# RACE — Communication Fairness Repairs (PASS 1)

## Defects fixed

### 1. Periodic baseline

`SimConfig.periodic_broadcast_s` now set positive in the PASS 1 pilot for treatment C (`300 s`). Periodic mode sends only on `periodic_broadcast` reason (task-bid path), not a silent no-op.

### 2. Matched random budget

Previously random charged **1** per allow while selective’s `n_bid_messages` counts **recipient fanout** (\(N-1\)), yielding ~261 vs ~129 messages.

**Fix:** `MatchedBudgetController` charges `n_recipients` per allow. Budget calibrated on development selective mean **before** test comparison (no per-test hindsight). PASS 1 calibration: **129** recipient messages / episode (mean selective bytes ≈ 59089).

Optional `MatchedByteBudgetController` exists for byte-matched variants.

### 3. Delayed full communication

Event-loop flood caused by rebroadcast-on-every-`message` delivery.

**Fixes:**

- Skip comm on `reason=="message"` for `full` / random / matched modes (`race_cooperative.py`).
- Pending bid deliver coalesce / supersede (`environment.py`: `_pending_bid_deliver_ids`, counters `n_bid_delivers_coalesced`, `n_bid_delivers_superseded`).
- Locked movements never rewritten by late messages (existing commitment gate).

Pilot includes delay ∈ {0, 30, 120} s and packet loss 10% at 30 s for full / selective / ecom.

### 4. Accounting identity

All treatments use identical instrumentation:

- `n_bid_messages` = recipient transmissions
- `n_bid_bytes` = serialized payload bytes
- Optional state-broadcast counters separate
- Coalesce / superseded deliver counts reported

### 5. Ratio statistics (labeled)

| Statistic | Definition |
|-----------|------------|
| **Ratio of mean bytes** | \(\bar{B}_t / \bar{B}_{\mathrm{full}}\) |
| **Mean of scenario-level ratios** | \(\mathrm{mean}_s(B_{t,s}/B_{\mathrm{full},s})\) |

Both emitted in `race_pass1_pilot_summary.json`. They are not interchangeable.

### 6. Generator / sensitivity notes

- Spatial mixture uses `pop_w` and `com_w` (`demand/generator.py`).
- Frozen original scenarios are not regenerated.
- Informative-OSM-candidate sensitivity must hold depot fixed (protocol note for PASS 2; not re-run in PASS 1 pilot).

## Fairness checklist for method comparisons

Same routing controller, charging, energy safety, request releases, fleet SOC, deadlines, and registry across A–G. Only the communication gate differs.
