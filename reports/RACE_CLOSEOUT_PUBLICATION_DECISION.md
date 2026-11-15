# Binding Publication Decision — Final Development Gate

## Decision: **PASS — Distinct method demonstrated** (narrow scope)

**Freeze for any future locked-final (not run here):**  
**RACE-COMM selective bidding + deadline-safe assignment timing + delay-aware peer trust**  
(`comm_mode=selective`, `assign_wait_mode=deadline_energy`, `delay_aware_trust=True`, `fair_physical_decisions=True`).

**Reject as primary novelty:** RACE-ECOM assignment certificates / PROVED dominance (Zhao et al. 2026 overlap; PROVED≈0).

## Why PASS (not PARTIAL / FAIL)

1. **Causal timing fixed.** None/periodic no longer wait for nonexistent peer bids; message/periodic no longer grant uncontrolled extra claims. Historical delayed “none drops OT” was confounded.
2. **EV-specific mechanism.** Commit-now vs bounded wait under hard TWs + irreversible commitments + conservative insertion — distinct from AC-DMTA’s certificate-silence loop.
3. **Credible improvement over selective on 60 development scenarios under delay:**  
   - 30 s: H − selective **+6.93 pp** OT (CI +4.7 to +9.2).  
   - 120 s: H − selective **+3.35 pp** (CI +2.0 to +4.8).  
   - H noninferior to none within **2 pp** pre-registered margin at both delays, with far fewer bytes than selective/full.
4. **Delay 0 honesty:** H = selective = event_triggered on OT/bytes; communication value is modest (+0.6 pp vs none, CI includes 0). Savings vs full remain large.

## What to claim in a manuscript

- Energy-safe cooperative online EV pickup with selective bids cuts bandwidth vs full at matched delay-0 service.  
- Under delayed links, **assignment timing and stale-bid distrust** dominate certificate messaging; waiting/deferring to delayed peers destroys OT; deadline-safe selective recovers near no-comm service.  
- Casablanca geography is the evaluation substrate; synthetic demand; not observed courier orders.

## What not to claim

- New general assignment-consistency theory beyond Zhao et al.  
- ECOM certificates as the empirical engine.  
- Delay-0 OT superiority of H over selective.  
- Locked-final results (not executed).

## Next step (analyst-gated only)

1. Freeze hyperparameters of H as above.  
2. Pre-register locked_final analysis plan.  
3. Run locked_final **once**.  
4. Write the manuscript with accurate scope (TR Part C only if locked results hold).

## STOP

No locked_final in this commit. No MARL restart. No Casablanca rebuild. No further open-ended stages.
