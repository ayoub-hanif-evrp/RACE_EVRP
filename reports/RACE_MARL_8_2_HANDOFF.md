# RACE-MARL Stage 8.2 — Handoff

## Verdict: **PARTIAL**

All previously missing *implementation / experiment* items from the Stage 8.2 prompt have now been executed. Empirical Gates 2–4 are still not scientifically cleared for a learned-method claim.

| Gate | Result | Evidence |
|------|--------|----------|
| 1 Correctness | **PASS** | Likelihood mask, GAE truncs, E battery, F≠D, bid-before-commit, strengthened tests |
| 2 Competent learning | **PARTIAL** | BC op-acc ≈ 0.97 after DAgger; validation OT ≈ 0.49 vs NL ≈ 0.83 |
| 3 Communication value | **PARTIAL** | NL selective causality + byte curve **PASS**; learned F≈C≈A on OT |
| 4 Distinctiveness | **PARTIAL / provisional negative** | Mechanism in code; learned outcomes do not yet isolate F |

**Locked final:** not launched.

## Completed follow-ups (this pass)

1. Weak assertions hardened (`test_marl_factorized_actions`, `reward_accounting`, `training_generalization`, causality).
2. Message causality unit tests: withheld / delivered / expired certificates.
3. Casablanca NL counterfactuals + delay: `stage82_causality_*.csv`.
4. Service-versus-byte curve: `stage82_service_vs_bytes_full.csv` (NL + learned).
5. Staged recovery curriculum A→B→F + matched C: `stage82_recovery_*`.
6. Greedy NL metric repaired (info_mode=full) in causality harness → OT 0.819.
7. `final_metrics` now exports `n_bid_messages` / `n_bid_bytes`.

## Key artifacts

- Reports: `reports/RACE_MARL_8_2_*.md`
- Results: `data/casablanca/online_results/stage82_*`
- Recovery ckpts: `stage82_recovery_checkpoints/`
- Scripts: `run_stage82_causality_and_bytes.py`, `run_stage82_recovery_curriculum.py`

## Remaining scientific work (not Stage 8.2 plumbing)

1. Close validation OT gap (more DAgger on validation-like states, freeze-op while training comm, longer budget, diagnose train-eval seed mismatch).
2. Only if Gate 2 clears: re-test learned F vs C on OT and bytes.
3. Then freeze method → locked_final.

No GNN. No fabricated positives. No locked_final until Gates 2–3 clear for the intended claim.
