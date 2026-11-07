# Stage 3A — Correctness preflight

## A1. Future energy leakage — FIXED

`projected_state_after_lock` now subtracts **conservative** remaining energy on unfinished legs (`path_length_m`), never `en_route_energy_kwh`.

Policy observations use `VisibleVehicleState` without hidden realized energy fields.

Tests: `tests/test_stage3a_preflight.py` (`test_projected_state_ignores_hidden_realized_energy`, `test_identical_obs_under_different_hidden_xi`).

## A2. Atomic fleet commits — FIXED

`commit_fleet_plans` is two-phase: validate → commit exact ordered plans without dispatch → activate legs. Full snapshot includes event queue; failures restore ownership, plans, vehicles, and `_eq`.

Test: `test_atomic_commit_rollback_restores_event_queue`.

## A3. Metric accounting — FIXED

- Claims counted only in `try_assign` / commit (first-time accepts), not again in `ActionInterface` / `_maybe_decide`.
- Planned energy rejections counted once at simulator level.
- Regenerated communication runs show `claims == served` for greedy/restricted one-shot claims (e.g. 10 served → 10 claims; 38 served → 38 claims).

## Dataset

`casablanca_release_v1` unchanged.
