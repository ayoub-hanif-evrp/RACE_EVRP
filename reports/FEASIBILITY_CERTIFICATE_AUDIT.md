# Feasibility certificate audit (Stage 1.5)

## Fixes

1. **Wrong pickup location** — `validate_schedule` now requires `to_node == request.snap_node` and path end equals snap node (`wrong_customer_node`).
2. **Operating shift** — Vehicles initialize at `shift_start_s = start_hour * 3600` (baseline 08:00). Customer service must finish by `shift_end_s = start + horizon`. Depot return may complete after shift end (documented). Overnight prepositioning from midnight is **not** allowed.
3. **Parallel edges** — Schedules record `path_edge_keys`; validator replays those keys when present.
4. **Fleet IDs** — Unknown / excess / malformed vehicle IDs still rejected (Stage-1 targeted fix retained).

## Adversarial tests

- `test_wrong_customer_node_rejected`
- `test_departure_before_shift_start_rejected`
- Prior coverage/return/timestamp/fleet tests retained

## Demonstrated certified baseline

`train/baseline_seed1` under generator `0.3.0`:

- Independently validated: `valid=true`
- 12 requests; vehicles used V1–V2; depot returns present
- Shift start 08:00; no midnight staging
- Min battery after ≈ 23.6 kWh (reserve 6 kWh) — still not energy-binding

## Policy note

Offline constructive witnesses have full request visibility. Certificates prove conditional route feasibility under the stated shift and physics, not online dispatch performance.
