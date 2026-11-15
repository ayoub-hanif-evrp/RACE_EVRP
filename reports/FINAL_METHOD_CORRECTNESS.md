# FINAL METHOD CORRECTNESS

**Tests:** `tests/test_race_csc.py` (+ regressions: timing, deadline wait, communication value, trust horizon, cooperative, protocol v2)  
**Runner:** `.venv` Python; all listed suites green (2026-11-15).

## Property evidence

### P1 — Exclusive ownership

- **Status:** Theorem-like from `TaskRegistry.try_claim` (central atomic map).
- **Tests:** `test_case_g_registry_exclusive_ownership`; integration episodes check registry vs `req.owner`.

### P2 — Commitment preservation

- **Status:** Invariant supported by simulator + tests (locked prefix / committed IDs).
- **Tests:** `test_case_j_locked_route_not_rewritten_silently`.

### P3 — Energy feasibility at claim

- **Status:** Invariant: claim path always re-runs `check_insertion` before `claim_task`.
- **Caveat:** Conservative vs **modeled** disturbances only — not absolute real-world energy safety.
- **Tests:** `test_case_e_energy_feasibility_gate_on_claim`.

### P4 — Bounded waiting

- **Status:** Conditional theorem: `assignment_wait_*` returns finite \(w\) from closed form; `immediate` ⇒ 0.
- **Assumptions:** scheduler fires `BID_ASSIGN_WINDOW`; no infinite reschedule loop.
- **Tests:** `test_case_f_tight_deadline_immediate_wait`; timing causality suite.

### P5 — Safe fallback

- **Status:** Invariant: empty/missing peers ⇒ `csc_should_claim` True if own feasible; delayed offer-only ignored.
- **Does not guarantee** ownership win or on-time service.
- **Tests:** cases B, H, L; unit `test_case_b_better_peer_offer_only_under_delay_does_not_block`.

### P6 — Message consistency

- **Status:** Invariant: withdrawn/expired/stale `commitment_version` excluded from credible set.
- **Tests:** cases D, I; peer trust unit tests.
- **Info boundary:** `test_info_boundary_known_versions_do_not_leak_peer_private_cv`; restricted peer insertion denied.

## Adversarial cases A–L

| Case | Result |
|------|--------|
| A better peer owns/intents | PASS — local blocked |
| B better peer never commits (offer-only delay) | PASS — local may claim |
| C delays 0/5/15/30/120 | PASS — episodes terminate; exclusive owners |
| D withdrawn/expired | PASS |
| E energy competition | PASS — feasibility gate |
| F tight deadline wait | PASS — immediate wait 0 |
| G simultaneous registry | PASS |
| H packet loss | PASS — no deadlock |
| I out-of-order versions | PASS |
| J charging/locked | PASS |
| K unused/confirm traffic counted | PASS — intent/owned counters when enabled |
| L no-comm / ignore-peer | PASS — terminates; exclusive owners |

## Unsupported as theorems

- Global optimality; real-world energy absolute safety.
- That `owned` messages imply eventual on-time service.
- That CSC improves OT over matched no-peer under delay (empirically **false** on pilot).

## Unresolved

- Whether a *different* credible signal (registry broadcast to claimants only) could restore delayed cooperation without speculative risk — **out of Prompt-1 scope** (one mechanism attempt only).
