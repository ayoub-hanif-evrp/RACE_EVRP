# RACE-MARL Stage 8.3 — Learning Recovery

## Curriculum map (Task 7) — `stage83_curriculum_map.json`

| Stage | What ran | Evidence |
|-------|----------|----------|
| A | Imitate validated intent bridge (weighted BC) | `stage83_bc_dagger_seed*.pt` |
| B | Eval before RL | recovery `bc_dagger_native_bridge` mean OT **0.629** |
| C | MAPPO no-comm, freeze_comm, val-select | `mappo_A` **0.628** |
| D | Peer-bid / selective certificates | `mappo_D` **0.629** |
| E | Selective + energy cert / ablation without peer energy | `mappo_F` / `mappo_E` **0.564** (seed-2 forget) |
| F | Limited joint fine-tune from A | 10 MAPPO iters; forgetting risk documented |

Checkpoint selection: validation OT on first **2** development scenarios every 5 MAPPO iters (disclosed; not locked final).

## Full recovery table (Task 9)

| Stage | Mean OT | Count |
|-------|---------|-------|
| greedy_charge70 | **0.819** | 6 |
| teacher_intent | 0.597 | 6 |
| bc_dagger_native_bridge | 0.629 | 18 |
| mappo_A / C / D | ~0.629 | 18 each |
| mappo_E / F | 0.564 | 18 each |

Training: 800 BC steps + 400 DAgger + 20 MAPPO iters × 3 seeds; wall ≈ 1.87 h.

## Conclusion

Recovery reached the factorized ceiling and includes the greedy reference. Learned selective communication does **not** improve service vs no-comm / random; F/E can regress under MAPPO.
