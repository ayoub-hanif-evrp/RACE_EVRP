# Stage 5.1 — Exact crosscheck

## Claims (separated)

| Claim | Meaning | Status |
| --- | --- | --- |
| A | Fixed pickup sequence + discrete charges: DP matches enum when enum serves the full order | **Pass** (`stage5_1_exact_crosscheck.json`, all four canned OK) |
| B | Full assignment/order optimality | **Not claimed** |
| C | Online CPU-bounded search | Approximate; timeouts observed |

Adapter: `src/race_casablanca/exact/dp_crosscheck.py`  
Tests: `tests/test_stage5_1_exact_crosscheck.py` (replaces weak Stage 5 structural-only check).

Seeded randomized tiny differential (8 instances, seed 42): no mismatches under claim A.
