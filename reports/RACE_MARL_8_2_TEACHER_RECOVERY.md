# RACE-MARL Stage 8.2 — Teacher Recovery

## Teachers

| Teacher | API | Role |
|---------|-----|------|
| Local greedy | `greedy_teacher_actions` | Legacy Stage 8.1 |
| Cooperative adapter | `CooperativeTeacherAdapter` | Maps `RaceCooperativePolicy` (`self_should_claim`, `selective_should_send`) onto factorized actions with restricted info only |

## Curriculum executed (`run_stage82_recovery_curriculum.py`)

For seeds `{0,1,2}`:

1. **A** — Cooperative BC (384 steps, 40 epochs, **3 DAgger rounds**) + MAPPO with `freeze_comm` on `A_no_comm` (25 iters).
2. **B** — Transfer → `B_full_comm` fine-tune (10 iters).
3. **C/E** — Transfer → `F_race_marl` selective gate + joint fine-tune (15+10 iters).
4. **D control** — From A init → `C_random_matched` with predeclared matched `p` (not labeled as learned comm).

## BC metrics (recovery Phase A, seed 0)

- op_accuracy ≈ **0.970**
- charge_accuracy ≈ **0.948**
- final_loss ≈ **0.080**

## Episode competence gap (honest)

| Setting | OT |
|---------|-----|
| NL selective (validation) | 0.832 |
| Training-side MAPPO eval (Phase B seed2, deterministic) | up to ~0.85 |
| **Validation** recovery A/B/F/C (3-seed) | **~0.49** |

Strong BC on labeled states + occasional high training-side eval does **not** transfer to the fixed validation pool under the current checkpoint-selection / distribution. Gate 2 remains **PARTIAL**.

Artifacts: `stage82_recovery_*`, `stage82_recovery_summary.json`.
