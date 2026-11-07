# Stage 2 — Simulator validation

## Scope

Validates the event-driven online simulator in `src/race_casablanca/sim/` against mandatory invariants. Does **not** claim that every Casablanca generated route was revalidated offline (Stage-1 release verification remains sampled).

## Test suite

| File | Focus |
| --- | --- |
| `tests/test_online_simulator.py` | Exact synthetic line-network routing/energy; greedy episode energy conservation; seed reproducibility |
| `tests/test_online_invariants.py` | Event time monotonicity; no unreleased requests in observations; exclusive task ownership; non-instantaneous movement; payload/depot unload; charging; delayed messages |
| `tests/test_online_policies.py` | Greedy, rolling-horizon LNS, limited-info baselines run on the same API |

Executed with project venv: **14 online tests passed** (plus existing travel-time tests still green after O(1) TTI index).

## Synthetic independent check

Line graph depot `0—1—2—3`, edges 1000 m, TTI factor 1 ⇒ free-flow 60 s/edge.

- Path `0→3`: length 3000 m, duration 180 s, nominal energy \(0.2\times 3=0.6\) kWh — matched by `RouteCache` + `EnergyModel`.
- Episode energy consumed equals \(0.2\times\) distance (km) under \(\delta=0\); battery drop matches consumption.

## Invariants enforced in code

1. **Causality** — event queue rejects arrivals scheduled before `now_s`; idle vehicles sync `ready_s ← max(ready_s, now_s)` before departure.
2. **No future leakage** — `observe_full` / available lists omit `UNRELEASED`; policies never open Stage-1 `witnesses/`.
3. **Ownership** — `TaskRegistry.try_claim` rejects duplicate owners.
4. **Motion** — travel uses cached free-flow paths + time-dependent TTI evaluation (same Stage-1 path semantics); no haversine dispatch.
5. **Energy** — planning uses conservative bound \((1+\delta)\); realization samples \(\xi\sim U[-\delta,\delta]\); reserve violations counted on realization.
6. **Payload** — load increases only at service end; depot unload zeros load.
7. **Charging** — depot-only; duration \(\Delta B/P^{ch}\); optional via `charge_on_return`.
8. **Reproducibility** — identical seeds reproduce metrics under stochastic energy.

## Stage-1 compatibility

`python scripts/verify_benchmark_release.py --light` → **ok**, 0 errors, 1 warning (Ahl Laghlam zero weight). Frozen `casablanca_release_v1` unchanged.

## Honesty limits

- Conservative energy guarantees hold only if the upper-bound model is valid; disturbances are **synthetic**, not measured Casablanca van energy.
- Rolling-horizon baseline is sequential insertion + relocate LNS with a wall-clock budget (**not** OR-Tools MIP). Returned plans are rechecked by the simulator feasibility module before commitment.
- Restricted-information mode still uses a **central ownership registry** (documented; not fully decentralized).
