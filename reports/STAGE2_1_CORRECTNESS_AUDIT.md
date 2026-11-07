# Stage 2.1 — Correctness audit

Frozen dataset: `casablanca_release_v1` unchanged. Commit baseline: Stage-2 `d492e8d` + Stage 2.1 corrections.

## Problems found (Stage 2 review) and fixes

| ID | Issue | Fix |
| --- | --- | --- |
| A | Restricted policy read true peer states via `sim.vehicles` / `check_insertion` | [`policy_api.py`](../src/race_casablanca/sim/policy_api.py): immutable obs + `ActionInterface`; restricted may only act on self |
| B | In-transit plan overwrite; feasibility from stale node | Locked prefix + `projected_state_after_lock`; inserts only into editable suffix |
| C | Reserve violations despite conservative bound | Pre-dispatch `check_leg_dispatch`; emergency stranded instead of unsafe travel |
| D | Non-atomic reassignment / RH release-then-reinsert | `try_reassign` validate-then-commit; `commit_fleet_plans` atomic RH apply |
| E | Weak tests | Adversarial suite: +δ energy, info isolation, lock immutability, forced charging |

## Acceptance checklist

1. Active leg not overwritten by new dispatch — **PASS** (`test_active_leg_immutable_*`)
2. No double / invalid completion — **PASS** (`_on_service_end` guards)
3. Bounded-energy conservative safety — **PASS** (adversarial tests + Casablanca OAT: 0 reserve violations)
4. Failed reassignment preserves source — **PASS** (`test_atomic_reassign_rollback`)
5. Restricted policies cannot observe hidden fleet state — **PASS** (`test_restricted_*`)
6. Charging / depot returns coherent — **PASS** (synthetic + `charge_on_soc035` with 8 charges)
7. Baselines produce defined metrics — **PASS** (`stage2_1_baseline_metrics.*`)
8. OAT factor isolation — **PASS** (`scripts/run_stage2_1_baselines.py`)

## Residual honesty

- Registry remains a **central ownership authority** (not fully decentralized).
- Safety guarantee holds only under the **declared** disturbance bound and pre-dispatch conservative gate.
- Hard customer deadlines: acceptance requires finish-by; in-service work is completed and marked on-time/late honestly.
