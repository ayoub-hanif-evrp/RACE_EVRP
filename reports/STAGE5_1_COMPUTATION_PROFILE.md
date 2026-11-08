# Stage 5.1 — Computation profile

## Changes

- Per-vehicle charge-schedule cache during neighborhood search.
- Incumbent constructed first; optimized plan commits only if lex-better and validated.
- Timeout retains verified incumbent (not a partial explore).
- Decision sources logged: `optimized` / `incumbent` / `safety`.

## Observed (peak SOC35, budget 0.5s)

| Policy | policy_runtime_s | timeouts | chose_opt / inc / safe |
| --- | ---: | ---: | ---: |
| race_rh | ~40–42 | 42–45 | 0 / 57 / 6 |
| sf_rh_07 | ~0 | 0 | n/a |

RACE-RH almost always selects the **incumbent** path; optimized neighborhood rarely improves the lex score within budget. Wall-clock DP work still exceeds the nominal 0.5s decision budget (noninterruptible inner calls) — reported as explicit timeout frequency, not hidden.

## Exactness note

Caching and early timeout do not change the inner DP’s discrete-action semantics when a full evaluation completes. Truncation means the outer search may miss improving neighbors — approximate online optimization (claim C), not exact assignment optimality (claim B).
