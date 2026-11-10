# RACE-MARL Stage 8.1 — Training repair

## Architecture (corrected)

```
local obs (own state + announced tasks + delivered peer-bid features)
        → shared encoder
        → operational head: claim / defer / charge
        → communication head: send_task_i / suppress
        → energy feasibility shield (ActionInterface)
```

Actor: `FactorizedActor` in `nets.py`.  
Critic: centralized concat obs (training only).  
Buffer: `FleetRolloutBuffer` with time-axis GAE + optional time-aware γ^(Δt/dt_ref).

## Behavior cloning warm-start

`marl/bc.py` clones a **local greedy teacher** (least-travel feasible claim; charge if SoC low; selective send when energy flex is tight). Teacher uses restricted `ActionInterface` only.

Pipeline (`scripts/run_stage81_repair.py`):

1. Collect BC batch on train factory.
2. Supervised clone (cross-entropy on both heads).
3. MAPPO fine-tune with corrected GAE.
4. Select checkpoints on **validation factory**, not train pool.

## Observation dimensions

| Block | Size | Units / notes |
| --- | ---: | --- |
| Base self/context | 16 | battery/40, load/600, time/28800, delay/120, … |
| Per task (×K=5) | 14 | own insertion (6) + peer summary (7) + own−peer travel Δ (1) |
| **Total `obs_dim`** | **86** | |

Peer summary (delivered bids only): best competing travel/energy/slack, age, validity, fresh count, pending assign window.

## Seeds / compute metadata

Recorded in checkpoint JSON / `stage81_summary.json`: PyTorch version, device, wall time, n_updates, ablation, relative checkpoint paths.
