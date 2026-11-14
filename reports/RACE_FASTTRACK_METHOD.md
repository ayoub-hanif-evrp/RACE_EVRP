# RACE-CERT — Fast-Track Method

**Provisional name:** RACE-CERT (decision-**cert**ifying energy-aware communication).  
**Not claimed novel a priori** — novelty depends on the EV-specific certificate + evidence.

## Strategic change

Stop training MAPPO to relearn routing/charging. Keep the Stage 8.3–validated **native cooperative routing controller** fixed. Concentrate research on **which energy-feasibility certificates to exchange** before irreversible pickup assignment under bandwidth and delay.

## Architecture

```
request_release → bid_exchange (comm only) → bid_assign (claim)
                      ↑
              pluggable send gate
         none|full|periodic|random|selective|certified|learned
                      ↓
         RaceCooperativePolicy._claim_pass / _maybe_charge
         (unchanged physical routing + charge-to-70%)
```

Implementation:

- `policies/race_cert_hybrid.py` — `RaceCertHybridPolicy` (routing frozen; comm specialized)
- `coordination/certifying_protocol.py` — heuristic interval certification
- `coordination/learned_comm_gate.py` — tiny BC send/suppress gate
- `scripts/run_race_fasttrack_pilot.py` — treatments A–G

## Information architecture

- Restricted observations only (no peer-truth escape hatch).
- Task-specific bids carry travel-primary cost, energy flex, slack, optional `[cost_L_s, cost_U_s]`.
- Atomic ownership + fresh `check_insertion` at commitment (bids never bypass physics).

## Pilot outcome (summary)

Hybrid parity OK. Selective and certified match full OT (~0.832) with ~65%/61% fewer bytes. Learned gate does not reduce traffic. **Decision: PARTIAL** — lead with non-learning selective/certifying communication; do not claim MARL routing or learned-comm superiority (see `RACE_FASTTRACK_DECISION.md`).

## What is *not* claimed

- No GNN/transformer.
- No joint MAPPO routing retrain.
- No theorem without stated assumptions (see certification report).
