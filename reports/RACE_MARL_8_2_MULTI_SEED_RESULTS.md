# RACE-MARL Stage 8.2 — Multi-Seed Results

## Initial Stage 8.2 matrix (3 seeds, 15 iters + light BC)

Learned validation OT ≈ **0.49** across A–F; NL selective/full ≈ **0.832**.  
Details: `stage82_summary.json`, `stage82_learned_ot_by_seed.csv`.

## Recovery curriculum (3 seeds)

Validation OT (mean ± std):

| Phase | Mean OT | Std |
|-------|---------|-----|
| A no-comm | 0.493 | 0.010 |
| B full-comm | 0.488 | 0.010 |
| F RACE-MARL | 0.489 | 0.008 |
| C random matched | 0.493 | 0.010 |

NL baselines (repaired greedy harness via causality script):

| Method | Mean OT |
|--------|---------|
| greedy_charge70 | 0.819 |
| nl_none | 0.821 |
| nl_selective | 0.832 |
| nl_full | 0.832 |
| nl_selective@30s | 0.801 |

## Bandwidth

See `stage82_service_vs_bytes_full.csv`. NL selective = same OT as full at ~22% of full bytes. Learned F ≈ C bytes ≪ B, but learned OT remains ~0.49.

## Checkpoint policy

Best training-side eval checkpoints (`*_best.pt`) used for validation reporting. Training-side OT can look much higher than validation (distribution shift / selection optimism) — validation numbers above are the scientific reference.
