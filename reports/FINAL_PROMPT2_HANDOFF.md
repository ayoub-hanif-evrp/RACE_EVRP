# FINAL PROMPT 2 HANDOFF

## Status

**COMPLETE** (demand 40/80/160 stress omitted by declared compute priority after primary/ablations/fleet/SOC).

## Frozen method

RACE-COMM Selective CSC-lite (`claim_mode=csc`, `send_claim_signals=False`, `deadline_energy`, `ttl_commitment`, `decentralized_signal`).

## Core development evidence (60 scenarios)

- @0 s: H = Full/Selective OT **84.24%**; ≈ **75%** fewer attempted bytes than full; +0.62 pp vs none (CI includes 0).  
- @15–30 s: H ≡ matched-wait zero-comm / placebo; **+6–8 pp** vs selective/full speculative deferral.  
- Confirmation and peer-energy message ablations: no OT gain.  
- Energy/runtime/packet accounting corrected and tested.

## Prompt 3 readiness

**YES** — method frozen; analysis plan written; locked_final still untouched.  
Execute confirmatory contrasts only; no algorithm redesign.

## Key paths

- Reports: `reports/FINAL_*.md` (Prompt 2 set)  
- Data: `data/casablanca/online_results/prompt2/`  
- Figures: `reports/figures/prompt2/`  
- Freeze: `configs/final_frozen.json`  
- Runner: `scripts/run_race_prompt2_dev_eval.py`
