# FINAL CAUSAL ABLATIONS

**Raw:** `data/casablanca/online_results/prompt2/race_prompt2_ablations.csv` (1440/1440 OK)  
**Delays:** 0 and 30 s on all 60 development scenarios.

## Mean OT by ablation

| Ablation | OT@0 | OT@30 | Attempted bytes@0 (approx role) |
|----------|------|-------|----------------------------------|
| A CSC normal | 0.8424 | 0.8336 | selective CSC-lite |
| A content withheld (ignore peers) | 0.8361 | 0.8336 | messages may send; claims ignore |
| A zero comm | 0.8361 | 0.8361 | 0 bytes |
| B immediate wait | 0.8424 | 0.8361 | |
| B legacy wait | 0.8424 | 0.8340 | |
| B deadline wait | 0.8424 | 0.8336 | |
| C defer TTL-valid offers | 0.8424 | **0.7700** | speculative deferral |
| C CSC-lite | 0.8424 | **0.8336** | |
| C no peer defer | 0.8361 | 0.8336 | |
| D confirm ON | 0.8424 | 0.8336 | extra intent/owned traffic |
| E strip peer energy fields | 0.8425 | 0.8336 | |
| F no readiness charge | **0.6029** | **0.5908** | shared charging matters |

## Mechanism isolation

**A — Message content:** At delay 0, CSC normal (+0.63 pp vs zero/withheld) shows peer-offer value. At delay 30, CSC normal ≡ content withheld (ignore) — delayed offers unused.

**B — Timing:** With CSC claim fixed, immediate/legacy/deadline waits are nearly tied at 0 s; at 30 s differences are small (0.8361 / 0.8340 / 0.8336). Timing alone does not explain the large G-vs-H gap.

**C — Speculative deferral:** Same wait; only claim rule changes. Defer-to-valid-offers loses **6.36 pp** vs CSC-lite at 30 s — the causal core of Prompt 1/2.

**D — Confirmation:** `send_claim_signals=True` matches CSC-lite OT at 0 and 30 s → **reject confirmation** (extra bytes only).

**E — Peer energy fields:** Stripping peer energy message fields leaves OT essentially unchanged (travel-primary ranking) → **no demonstrated message-level energy information value**.

**F — Charging:** Disabling readiness charge collapses OT (~60%) — confirms charging is operationally material, but it is **shared** across primary communication treatments and is not the CSC novelty claim.
