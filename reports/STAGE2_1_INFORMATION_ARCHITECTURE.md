# Stage 2.1 — Information architecture

## Boundary

Policies no longer receive a mutable `OnlineSimulator`.

| Mode | Observation | Actions |
| --- | --- | --- |
| Full | `FullInfoObservation`: all vehicles (deep copy), announced available tasks, released requests | `check_insertion` / `claim_task` for any vehicle |
| Restricted | `RestrictedObservation`: own state, own commitments, public announcements, **delivered** peer snapshots only | `check_insertion` / `claim` / `broadcast` **self only** (`PermissionError` otherwise) |

Implementation: [`src/race_casablanca/sim/policy_api.py`](../src/race_casablanca/sim/policy_api.py).

## Central registry

`TaskRegistry` enforces exclusive ownership (atomic claims). It does **not** publish peer SOC/location. Systems using it are **not** fully decentralized; message and claim costs are counted in metrics (`n_messages`, `n_claims`, `n_failed_claims`, `mean_info_age_s`).

## Delayed messages

`MessageBus` delivers state updates after `message_delay_s`. Restricted peers appear in `obs.peers` only after delivery. Untouched peers are absent — verified by `test_restricted_observation_hides_peer_true_state`.

## Empirical note (after leak fix)

On `baseline_seed1` at full SOC, full vs restricted still tied at 10/12 served (distance differs). On `peak_stress_seed2`, full greedy **38/40** vs restricted **35/40** — a measurable coordination gap once information is truly restricted.
