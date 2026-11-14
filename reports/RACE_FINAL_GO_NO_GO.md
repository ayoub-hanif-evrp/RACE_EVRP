# RACE PASS 1 — GO / NO-GO for PASS 2

## Decision: **CONDITIONAL GO** (narrowed claims)

Do **not** proceed to locked final testing with a claim that RACE-ECOM dominates selective on service. Proceed only if PASS 2 hypotheses are rewritten to match evidence.

## What passed (mandatory defects)

| Gate | Status |
|------|--------|
| Public fleet roster; incomplete coverage blocks false cert | **PASS** |
| Adversarial silent-best competitor | **PASS** |
| Heuristic intervals not oversold as safety theorems | **PASS** (docs + code) |
| Periodic baseline with positive period | **PASS** |
| Matched random ≈ recipient budget (dev-calibrated) | **PASS** |
| Delayed full event-loop (0/30/120) + loss stress | **PASS** |
| Fair byte / message instrumentation + dual ratio stats | **PASS** |
| Deterministic correctness tests | **PASS** (`test_race_ecom_pass1`, cert tests) |
| Causal incomplete-coverage / delay / matched tests | **PASS** |
| Development pilot A–G executed | **PASS** |

## What failed relative to a top-tier “new method wins” story

| Claim | Evidence |
|-------|----------|
| ECOM > selective on OT | **FAIL** — identical 157/192, identical owners at delay 0 |
| Useful PROVED certificates in the wild | **FAIL on this pilot** — mean `n_ecom_proved` = 0 |
| ECOM bytes < selective at delay 0 | **FAIL** — 63227 vs 59089 |
| Peer messaging always helps under delay | **FAIL** — none/periodic can beat full/selective at 30–120 s |

## What remains scientifically usable

1. **Correct certification semantics** (roster + unknown competitors + A/B/C labels) — necessary for any cert paper; previously wrong.
2. **Fair communication science** (periodic, matched random, delayed full) — enables honest baselines.
3. **ECOM under delay:** similar OT to selective with **lower** traffic (esp. 120 s: 145 vs 277 msgs) — secondary, delay-regime finding only.
4. **Selective RACE-COMM** remains the strongest delay-0 bandwidth/service point among correct protocols.

## PASS 2 authorization conditions

Analyst may authorize PASS 2 **only if** primary hypotheses are:

1. Coverage-correct, decision-critical communication with explicit non-PROVED fallbacks is scientifically sound; and/or  
2. Selective (or ECOM) is **non-inferior** to full on OT within a **pre-registered margin**, at substantially lower bytes; and/or  
3. Under delayed links, ECOM reduces traffic vs selective without large OT loss (pre-register noninferiority).

**Forbidden as primary PASS 2 claim without new evidence:** “RACE-ECOM certificates prove unique winners and improve fleet service.”

No locked-final run until analyst confirms the narrowed plan. **STOP here.**
