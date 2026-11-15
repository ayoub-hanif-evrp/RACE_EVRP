# FINAL METHOD MATHEMATICS — RACE-COMM / CSC-lite

## 1. System model

- Vehicles \(V=\{v_i\}\), dynamic pickups \(R_t\) released online.
- Local observation \(o_i(t)\): own state, announced open tasks, delivered peer bid payloads only.
- Travel: time-dependent Casablanca graph; energy: conservative insertion checker with reserve SOC.
- Locked route prefix immutable; editable suffix for insertions.
- Messages: delayed / lossy `task_bid` bus; ages via `as_of_s`, TTL `expires_s`, `commitment_version`.
- Atomic registry \(\mathcal{R}\): unique owner per request (central authority; not a global router).

### Information partition

| Object | Public | Private to EV | Via messages | Registry | Env wait scheduler |
|------|--------|---------------|--------------|----------|--------------------|
| Fleet IDs | yes | — | — | — | yes |
| Own battery/plan | — | yes | optional snapshots | — | — |
| Peer physics | — | no | optional stale snapshots | — | **no** under `decentralized_signal` |
| Peer bids | — | — | delivered only | — | local_bids coverage count |
| Ownership | — | — | `owned` flag if sent | authoritative | — |

Architecture label: **partially decentralized / registry-assisted**, with **decentralized-signal** assignment waits (no cross-fleet insertion probe by default).

## 2. Lexicographic objective

1. Maximize on-time completed pickups (hard TW).
2. Minimize travel / charging burden among feasible policies.
3. Minimize communication bytes and assign-wait latency.
4. Preserve ownership exclusivity and physical commitment safety.

Hard feasibility is **never** collapsed into a soft penalty in the claim gate.

## 3. Commitment states (task coordination)

`UNRELEASED → AVAILABLE → (OFFERED)* → CLAIMED → IN_SERVICE → COMPLETED | EXPIRED/MISSED`

- **OFFERED:** feasible bid without `claim_intent`/`owned` (nonbinding).
- **CLAIMED:** registry accept (authoritative).
- Optional signals: `claim_intent` (intention), `owned` (asserted registry success) — **disabled** in frozen CSC-lite.

No soft reservations that block work indefinitely.

## 4. Commitment-safe claim rule

Let \(\mathcal{P}_i(r)\) be fresh peer bids for request \(r\) at time \(t\).

**Credible set** \(\mathcal{C}_i(r)\):

- If `message_delay ≈ 0`: all trustworthy feasible peers (offers rank).
- If `message_delay > 0`: only peers with `owned ∨ claim_intent` (and trustworthy under `ttl_commitment`).

Claim iff own bid is best in \(\{b_i\} ∪ \mathcal{C}_i(r)\) and no peer has `owned`.

Then: re-check `check_insertion(self, r)`; `registry.try_claim`.

### Assignment wait (deadline_energy)

\[
w = \min(d,\; s - u - \tau^+,\; w_{\max})
\]
or \(w=0\) if delay eats slack fraction, urgency, no competitors, or peer coverage complete.

Under `decentralized_signal`, \(\tau^+\) (best fleet travel) is **not** probed; wait uses TW/delay/roster/local table only.

## 5. Pseudocode (executable-level)

```
on release(r):
  for each v: exchange bids (selective send)
  w ← assignment_wait_for_request(r)   # finite, TW-aware
  schedule bid_assign at now+w

on bid_assign / physical opportunity for v:
  for r in announced sorted by tw_end:
    b ← compute_self_bid(v, r)
    peers ← delivered bids for r
    if not csc_should_claim(b, peers, delay, known_versions_from_inbox):
      continue
    if not check_insertion(v, r).feasible: continue
    if registry.try_claim(r, v): commit; invalidate other ads; break
```

**Tunable parameters (minimal):** `bid_ttl_s=180`, `max_assign_wait_s=60`, `urgency_slack_s=180`, `delay_slack_frac=0.35`. No urgency prices.

## 6. Complexity

Per decision: \(O(|R_{\mathrm{open}}| · I)\) insertion checks for self only (+ selective sends). Registry claim \(O(1)\).

## 7. Conditional guarantees (see CORRECTNESS)

Exclusive ownership follows from \(\mathcal{R}\). Bounded wait follows from closed-form \(w\). Safe fallback: missing peers ⇒ claim if locally feasible (not a completion guarantee).
