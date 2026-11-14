# RACE-ECOM — Final Method Formulation (PASS 1)

**Status:** PASS 1 development freeze candidate (pending analyst GO).  
**Primary code:** `src/race_casablanca/coordination/race_ecom.py`, `certifying_protocol.py`, `policies/race_cert_hybrid.py`.  
**Operational core (frozen):** native cooperative routing + charge-to-70% + conservative feasibility (`RaceCooperativePolicy` / hybrid wrapper).

## 1. Problem (information-theoretic)

Online multi-agent EV pickup fleet on a known road graph with time-dependent travel.

| Symbol | Meaning |
|--------|---------|
| \(\mathcal{V}\) | Public fleet roster (vehicle IDs only) |
| \(\mathcal{R}(t)\) | Publicly announced open requests with hard windows |
| \(x_i(t)\) | Private vehicle state (pose, SOC, payload, commitments) |
| \(\mathcal{C}_i\) | Locked irreversible in-progress commitments of \(i\) |
| \(\mathcal{M}\) | Delayed / lossy peer messages (task bids / certificates) |
| Registry | Minimal atomic ownership arbitration (not fully decentralized) |

**Public:** roster IDs, request announcements, ownership registry outcomes.  
**Private:** full vehicle physics, local insertion costs, unread peer states.  
**Transmitted:** task-bid payloads (travel-primary score + energy/slack tie fields + optional interval metadata).  
**Coordinator:** registry claims only; routing remains local after ownership.

**Objective (lexicographic, service-first):** maximize on-time served requests; then minimize excess energy risk / drive; communication is a cost in experiments, not in the dispatch score unless noted.

**Bid ranking (unchanged primary key):** `marginal_travel_s` ascending; residual energy and deadline slack are tie-breakers only (A1). Changing this ranking is an isolated experimental factor, not done in PASS 1.

## 2. What is *not* claimed as novelty

- The dominance inequality \(U_j < \min_i L_i\).
- Standard selective / event-triggered bidding.
- Native cooperative insertion routing itself (already validated; stronger than factorized MARL).

## 3. RACE-ECOM algorithm

### 3.1 Public roster coverage

Competitor count = \(|\mathcal{V}| - 1\), from `obs.fleet_vehicle_ids`, **never** from `len(obs.peers)`.

Silent / undelivered competitors ⇒ **incomplete coverage** ⇒ certificate status ≠ PROVED.

### 3.2 Certificate statuses (never conflated)

| Label | Meaning |
|-------|---------|
| **A PROVED** | Unique travel-primary winner under complete roster coverage + declared intervals |
| **B HEURISTIC** | Choice under incomplete / aged information |
| **C FALLBACK** | Safe detailed bid without certification claim |

Age-widened peer intervals \([c-w(\Delta), c+w(\Delta)]\) with \(w(\Delta)=\min(180, 5+0.15\Delta)\) are **heuristic** (A3), not Lipschitz certificates.

### 3.3 Decision-critical send rule (`ecom_should_send`)

1. Build local intervals for self (point) and fresh peers (heuristic widen).
2. If roster competitors lack fresh certificates → incomplete → send only for initial representation / near-expiry refresh; else await (B/C).
3. If PROVED unique winner → suppress redundant loser traffic; refresh only near expiry for the winner.
4. If ambiguous among represented set → send if own bid could change the ranking (rate-limited).
5. Material commitment / feasibility changes → always send (FALLBACK).
6. Dispatch uses frozen insertion controller; physics re-checked at commitment.

### 3.4 Pseudocode

```
ECOM_SHOULD_SEND(own, peer_bids, memory, now, fleet_ids):
  n_comp ← |fleet_ids| − 1_{self ∈ fleet_ids}
  cert ← CERTIFY(own, peer_bids, now, n_announced_peers=n_comp)
  if memory is None:
    return send if own.feasible (status FALLBACK if n_comp>0 else PROVED)
  if material_change(memory.bid, own): return SEND FALLBACK
  if incomplete_coverage(cert):
    return SEND FALLBACK near expiry else SUPPRESS HEURISTIC
  if cert.certified:
    return SUPPRESS PROVED (refresh winner near expiry only)
  if own in ambiguous or locally_best:
    return SEND HEURISTIC (rate-limited)
  return SUPPRESS or expiry FALLBACK
```

### 3.5 Complexity

Per decision epoch with \(R\) open tasks, \(N\) vehicles, \(P\le N-1\) peer bids/task:  
\(O(R \cdot (P + \log P))\) for certify + best-bid sorts. Message fanout \(O(N)\) per send. No GNN / transformer.

### 3.6 Conditional proposition (assumptions required)

**Proposition (conditional zero travel-primary regret within covered set).**  
Under A1–A4 (see `certifying_protocol.py`), if every roster competitor is represented by a fresh interval and \(U_j < \min_{i\neq j} L_i\), then \(j\) uniquely minimizes travel-primary cost among that set; further detailed bids cannot change the travel-primary ranking *within the set* without violating a peer interval. Physics remains independently gated. Incomplete coverage voids the claim.

**Proof sketch.** Point/interval construction + standard interval dominance; missing agents violate the premise by construction of `n_announced_peers`.

## 4. Baselines sharing the same operational core

A none · B full · C periodic (`periodic_broadcast_s>0`) · D random matched (recipient-fanout budget from selective on train/dev) · E selective · F certified (prior heuristic) · G ecom.

Centralized greedy / RH references retain more information; noted separately in PASS 2.

## 5. Learning extension

Deferred. Prior BC/learned gate ≈ full volume. Paper does not depend on learning if ECOM/selective stands alone.
