# FINAL METHOD INFORMATION BOUNDARIES

## Architecture label

**Partially decentralized / registry-assisted**, with **decentralized-signal** assignment waits.

Not fully decentralized: a central `TaskRegistry` enforces exclusive ownership.  
Not a centralized fleet optimizer: the registry does not solve global routing.

## Per-EV decision API (`RestrictedObservation` + `ActionInterface`)

**May use**

- Own visible state (node, battery, load, mode, committed IDs, locked leg).
- Announced open tasks (public releases).
- Delivered `peer_bids` payloads only (as_of, expires, costs, flags, commitment_version).
- Public fleet ID roster.
- `check_insertion(self, request_id)` only.
- `claim_task(self, …)`, `broadcast_task_bid(self, …)`.

**Must not use**

- Live peer physics via `get_simulator()` (raises `PermissionError`).
- `check_insertion(peer_id, …)` (PermissionError).
- Another EV’s private `_own_commit_version` without a delivered message (`_known_versions_for` test).

## Shared policy object hygiene

| Store | Scope |
|-------|--------|
| `_own_commit_version[vid]` | Own EV only in claim kwargs |
| `_peer_commit_known[viewer][sender]` | Updated only from that viewer’s delivered bids |
| `_sent` | Per (vehicle, request) send memory |

## Assignment wait authority

| Mode | Cross-fleet `sim.check_insertion` | Used by frozen method |
|------|-----------------------------------|------------------------|
| `decentralized_signal` (default) | **No** — TW, delay, roster size, one local_bids coverage view | **Yes** |
| `coordinator_assisted` | Yes — documented env authority only | No (ablation / legacy diagnosis) |

Env still invokes `assignment_wait_for_request(sim, rid)` centrally to schedule `BID_ASSIGN_WINDOW`; that is a **timing authority**, not a global assignment solver.

## Registry

Authoritative owner map. Duplicate claims increment `n_rejected_duplicates`. Restricted EVs learn ownership via execution outcomes and optional `owned` messages (disabled in CSC-lite).
