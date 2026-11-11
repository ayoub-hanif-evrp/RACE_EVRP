# RACE-MARL Stage 8.2 — Causal Coordination Audit

**Status:** PASS (protocol + unit + NL counterfactual evidence)  
**Base:** Stage 8.1 MAPPO repairs retained; Stage 8.1 artifacts preserved under `marl_*`.

## Mechanism distinction (D vs F)

| Variant | Communication policy | Environment constraint |
|---------|----------------------|------------------------|
| `D_selective` | Learned send/suppress on any feasible announced task | Free selective mask |
| `F_race_marl` | Learned send/suppress **only** when an energy certificate is decision-relevant | Send mask gated by contest / tight energy flex / tight deadline / pending assign window; payloads tagged `energy_certificate=True` |

## Bid-before-commit protocol

1. Collect factorized (op, comm) proposals.  
2. Execute communication first; zero-delay deliveries ingest immediately.  
3. Batched, vehicle-order-invariant claim resolution.  
4. Defer when a better fresh peer certificate exists (`self_should_claim`).  
5. Fresh feasibility at commitment; then physics.

## Counterfactual evidence

### Unit (deterministic)

- Superior peer certificate ⇒ `self_should_claim` flips; V1 defers (`n_claim_defers_to_peer ≥ 1`).
- Expired certificate ⇒ V1 still claims (stale cert ignored).
- Tests: `tests/test_marl_message_causality.py`.

### Casablanca validation (non-learning, matched exogenous)

Artifact: `stage82_causality_deltas.csv`, `stage82_causality_bytes_summary.json`.

| Contrast | Mean owner Hamming vs selective@0 | Mean OT delta vs selective@0 |
|----------|-----------------------------------|------------------------------|
| nl_none (withheld) | **14.17** | −0.011 |
| nl_selective@30s (delayed) | **14.50** | −0.031 |
| nl_full@0 | 0.00 | 0.000 |
| greedy_charge70 | 5.33 | −0.013 |

Selective vs none also records mean `n_defers_to_peer = 10.5` under zero delay (decision changes from delivered bids). Delayed selective loses those defers (0.0) and loses ~3pp OT.

**Learner never received counterfactual outcomes as privileged labels.**
