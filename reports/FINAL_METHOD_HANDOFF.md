# FINAL METHOD HANDOFF — Prompt 1 → Prompt 2

## Decision

**PARTIAL.** Do **not** start a second new mechanism.

## Frozen method for Prompt 2

**RACE-COMM Selective + commitment-safe claim (CSC-lite)**

```text
RaceCooperativePolicy(
  comm_mode="selective",
  claim_mode="csc",
  send_claim_signals=False,
  assign_wait_mode="deadline_energy",
  peer_trust_mode="ttl_commitment",
  wait_authority="decentralized_signal",
  fair_physical_decisions=True,
  max_assign_wait_s=60.0,
)
```

## One-line scientific claim (honest)

Selective EV bidding remains useful at zero delay; under message delay, nonbinding peer offers must not drive deferral — doing so loses ~11–16 pp on-time on the pilot; commitment-safe claim restores matched no-peer service without productive confirmation traffic.

## Prompt 2 should

1. Expanded development ensemble evaluation of the frozen config (still **not** locked_final until authorized).
2. Report zero-delay communication–service Pareto vs none/full.
3. Report delayed null: CSC-lite ≡ matched no-peer for ownership/OT.
4. Keep historical negative findings (ECOM, MARL, trust-horizon H_CURRENT).

## Do not

- Reintroduce claim_intent as a “win” without new evidence.
- Claim TR Part C readiness from six scenarios.
- Run locked_final in Prompt 2 unless separately authorized.
