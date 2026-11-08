# Stage 5.1 — State and charging audit

## Projection bug (fixed)

`projected_state_after_lock` previously treated every busy vehicle as mid-leg and re-subtracted `path_length_m` energy. After arrival, mode is `SERVING` or `CHARGING` while path metadata can remain — double-counting travel energy and corrupting readiness.

Mode-specific projection now:

| Mode | Behavior |
| --- | --- |
| EN_ROUTE | Deduct remaining conservative travel; project arrival + service/charge |
| SERVING | Keep current battery/node; remaining service time; add payload once |
| CHARGING | Keep pre-charge battery; project to `target_kwh` with remaining duration; no depot re-leg |
| IDLE | Current state |

Tests: `tests/test_stage5_1_projection.py`.

## Undercharging (addressed, not sufficient)

RACE-RH evaluated charging mainly as support for current pickups. Empty plans preferred zero charge. Shared `ReadinessChargingController` (default target 0.70) now charges idle empty vehicles when SOC is below target, unless urgent claimable work exists. Equalized for charge-aware SF-RH.

Ablation peak SOC35: race_rh **33/40** vs race_rh_no_ready **30/40** — readiness recovers 3 pickups, still below greedy_07 **36/40**.
