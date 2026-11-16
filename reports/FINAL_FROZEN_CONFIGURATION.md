# FINAL FROZEN CONFIGURATION

**Machine-readable:** `configs/final_frozen.json`  
**Prompt 1 SHA:** `a725992ab58b70c44d7faaff380dcfd47618b027`  
**Prompt 2 SHA:** filled at push (see handoff).

## Method name

**RACE-COMM Selective with Commitment-Safe Claim (CSC-lite)**

## Exact parameters

```python
RaceCooperativePolicy(
    comm_mode="selective",
    claim_mode="csc",
    send_claim_signals=False,
    assign_wait_mode="deadline_energy",
    peer_trust_mode="ttl_commitment",
    wait_authority="decentralized_signal",
    fair_physical_decisions=True,
    max_assign_wait_s=60.0,
    urgency_slack_s=180.0,
    bid_ttl_s=180.0,
    enable_readiness_charge=True,
    charge_target_soc=0.70,
    rng_seed=7,
)
```

## Architecture statement

**Partially decentralized / registry-assisted multi-agent pickup coordination.**

- Central atomic ownership registry.  
- Shared simulator schedules assignment windows from declared timing/communication signals (`decentralized_signal`: no cross-fleet energy travel probe).  
- EVs compute restricted local bids and claim under CSC rules.  
- Physical energy feasibility is the claim-time insertion checker — **not** the wait formula.

## Locked-final matrix (Prompt 3)

Treatments: A NONE_NOW, B FULL, G SELECTIVE_VALID_PEER, H CSC_LITE, I MATCHED_WAIT_ZERO_COMM, J MESSAGE_PLACEBO (optional F legacy).  
Delays: 0, 30, 120 (and 15 if budget).  
Do not retune after seeing locked outcomes.

## Data governance

- Prompt 1 pilot = train-side development.  
- 60-scenario `evaluation_v1/default` = development (prior exposure).  
- `evaluation_v1/locked_final` = untouched independent test.  
- Requests are synthetic; geography is Casablanca.
