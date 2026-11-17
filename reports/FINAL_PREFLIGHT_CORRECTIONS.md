# FINAL PREFLIGHT CORRECTIONS (Prompt 3)

## Scope

Comparator validity only. CSC-lite parameters and claim/wait/trust logic were not retuned.

## Correction A — Random BYTE_MATCHED

### Defect

Prompt 2 estimated `typical_payload_bytes = matched_budget / (2 * n_recipients)`, so one “payload” absorbed a large fraction of the episode budget. Random traffic collapsed (~2 kB vs CSC ~56 kB).

### Fix

`MatchedByteBudgetController.allow(..., payload_bytes=)` charges **actual serialized payload × recipient fan-out**. `RaceCooperativePolicy` (`comm_mode="random_matched_bytes"`) serializes the candidate message, asks the controller with that size, then broadcasts only if allowed. Invalidation/commitment traffic is included in attempted bytes via the same simulator accounting path.

### Training-only calibration

Scenarios (development, not locked_final):

`baseline_seed{1,4,7}`, `peak_stress_seed{2,5,8}`, `tight_windows_seed{3,6}`.

| Quantity | Value |
|---|---|
| CSC-lite mean attempted bytes | 55 364.75 |
| Random budget (declared) | 55 364.75 |
| Random mean attempted bytes | 49 712.75 |
| Ratio random/CSC | **0.898** (~10.2% under) |
| Locked_final mean random (delay 0) | 49 030.3 |
| Locked_final mean CSC (delay 0) | 55 306.5 |
| Locked ratio | **0.887** |

Disparity is reported honestly (within ~10–15% training target). Stochastic send under a fixed episode budget; RNG seed = policy `rng_seed`.

Artifacts: `data/casablanca/online_results/prompt3_preflight/`.

## Correction B — Periodic communication

### Defect

Runner set `periodic_state_broadcast=True` without positive `periodic_broadcast_s` (default 0) → no timer events → zero task-bid bytes.

### Fix

- `periodic_broadcast_s = 300.0`
- `periodic_state_broadcast = False` (task-bid comparator, not state snapshots)
- Initial eligible-bid send at first decision opportunity, then refresh every 300 s
- Same physical claim/charge opportunities as other treatments (`fair_physical_decisions=True`)

Training mean attempted bytes: **48 090.25** (8/8 episodes positive). Locked_final delay-0 mean: **48 863.7**.

## CSC-lite freeze check

Reproduced development CSC-lite OT under frozen config; max |ΔOT| vs Prompt 2 H@0 reference = **0**. Full-comm / no-comm paths unchanged by comparator fixes. Content hashes recorded in `configs/final_locked_manifest.json`.

## Tests

`tests/test_prompt3_baseline_fixes.py`: real payload×fanout budgeting, reproducibility, budget exhaustion, periodic 300 s fire + positive bytes, no future-request access, physical claim parity.

## Freeze-version record

| Role | SHA |
|---|---|
| Immutable CSC-lite implementation | `deb750af7edebdc8868eed2af6fa389e77765136` |
| Prompt 2 freeze metadata commit | `3e25c5458cb4799f521b63c537950eb702619084` |
| Prompt 3 evaluation commit | *(this push; see FINAL_PROMPT3_HANDOFF)* |
