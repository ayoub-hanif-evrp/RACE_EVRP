# FINAL CAUSAL FINDINGS (Prompt 3)

Locked_final evidence, confirmatory contrasts only for primary claims.

## What received peer information changed

### Zero delay

- H, B, E, F, G share **identical** on-time service and ownership maps (Hamming 0 among these).
- Relative to A/I/J: mean +0.61 pp OT; mean owner Hamming ≈ 9.9 vs A/I — peer bids **can** change ownership, but the service CI includes zero.
- Event-triggered equals CSC-lite exactly → selective CSC-lite does **not** demonstrate a distinct zero-delay information-processing advantage beyond the shared selective/event traffic pattern.

### Positive delay (30 s)

- H ≡ I ≡ J (service and ownership).
- Therefore delayed peer bids under CSC-lite are **not used for allocation benefit**; any residual traffic is operationally unused relative to matched wait without messages.
- G/F/B defer to nonbinding delayed offers and lose **~8 pp** OT vs H/I. Causal reading: **unsafe trust of delayed offers**, not “more communication helps.”

### Longer delay (120 s)

- H ≡ I again (null delayed-information effect persists).
- G and B align with H (deferral harm attenuated or path converges); F remains harmed (+2.39 pp H−F).

## Speculative-deferral effect

Commitment-safe claim (offer ≠ ownership; defer only to claim-intent / owned offers under delay) **prevents** the large 30 s collapse seen in selective-legacy / valid-peer / full. This validates a coordination-safety rule.

## No-peer equivalence under delay

Matching assignment wait without peer bids (I) reproduces H exactly at 30 s and 120 s. Placebo messages (J) also match. Multi-agent message value under delay is **not supported** as an allocation mechanism on this benchmark.

## Honest causal summary

1. Zero-delay selective bidding reproduces full bidding with far fewer bytes.  
2. That efficiency is shared with event-triggered communication.  
3. Delayed peer information, when handled safely, matches zero-peer matched wait.  
4. Handling delayed offers as if binding destroys service.
