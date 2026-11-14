# Closest Prior Art — Assignment Consistency & Event-Triggered Coordination

Reviewed for the analyst-mandated PASS-1 follow-up (commit baseline `c8e1eea`).

## 1. Zhao et al., 2026 — AC-DMTA

**Citation:** Zhao et al., *Assignment-Consistent Dynamic Multi-UAV Task Allocation*, *Drones* 2026, DOI `10.3390/drones10070523`.

### What they already do

| Axis | AC-DMTA |
|------|---------|
| Information | Local asymmetric / stale neighbor records; time-varying delayed & lossy links |
| Cost model | Point bids → **interval bids** over age-expanded uncertainty envelopes (motion, energy, status) |
| Certification | **Task-winner stability** and **bundle stability** certificates; communicate only if certificates fail |
| Communication | Decision-triggered / targeted packets; silence when assignment-irrelevant; guard-interval retries under delay |
| Deconfliction | Timestamp / recency-aware fusion; path-version invalidation |
| Guarantees | Local *sufficient* conditions within modeled envelopes & competitor sets — **not** global optimality |
| Evaluation | Four simulated benchmarks, delay & packet loss, paired seeds |

Core hypothesis (verbatim spirit): communicate when stale information **may change the assignment**, not on every state change.

### Overlap with RACE-ECOM

- Interval bids + age widening
- Winner-stability / dominance-style certificates
- Suppress assignment-irrelevant messages
- Explicit delayed / lossy communication evaluation

**This is substantial conceptual prior art.** RACE-ECOM’s \(U_j < \min_i L_i\) gate and “decision-critical send” are not a new general principle relative to AC-DMTA.

## 2. Event-triggered adaptive consensus (CBBA-ETC), 2026

**Citation:** *Event-triggered adaptive consensus for multi-robot task allocation*, *Computer Communications* / arXiv:2604.06813, 2026.

| Axis | CBBA-ETC |
|------|----------|
| Triggers | Initial plan, significant bid Δ, high-value conflict opportunity, adaptive time fallback |
| Goal | Cut CBBA-like consensus traffic while retaining task-completion |
| Domain | Heterogeneous robot swarms; Behavior Trees; some energy models in sims |
| Certificates | Event heuristics, **not** interval assignment-consistency theorems |

Overlap with RACE-COMM **selective** (material change / contest / expiry) is strong; less overlap with certification-centric ECOM than AC-DMTA.

## 3. Earlier lineage (already noted in PASS 1)

ED-CBBA (2025), Otte et al. lossy auctions, classical CBBA/ACBBA — communication-efficient or delay-robust allocation without EV irreversible pickup locks as the scientific object.

## 4. Precise comparison table (RACE vs AC-DMTA)

| Dimension | AC-DMTA (Zhao 2026) | RACE-ECOM / RACE-COMM |
|-----------|---------------------|------------------------|
| Platform | Multi-UAV CBBA-style bundles | Ground EV fleet, Casablanca road graph |
| Energy | Envelope energy in interval bids | Conservative insertion + charge-to-70% + reserve gate |
| Commitments | Bundle / path-version repair | **Irreversible in-progress route locks**; physics re-check at claim |
| Deadlines | Task windows in feasibility | Hard pickup TWs; service-first OT metric |
| Ownership | Distributed winner tables | **Atomic central registry** + local bids (not fully decentralized) |
| Intervals | Motion/energy/status envelopes with claimed soundness under model | Heuristic travel wideners; **explicitly non-theorem** after PASS 1 |
| PROVED empirics | Certificate-driven silence is the method | Pilot PROVED count ≈ 0 after honest roster coverage |
| Delay interaction | Guarded certificate retry | Two-phase assign wait ∝ message delay (see diagnosis) |

## 5. Verdict on “application domain ≠ novelty”

Transplanting assignment-consistency certificates to electric parcel pickups **is not automatically a methodological contribution**. Zhao et al. already cover stale intervals, winner certificates, decision-triggered communication, delay, and loss.

Any remaining RACE distinction must be **technical and consequential**, not branding:

1. Irreversible locked EV routes + conservative energy insertion under hard TWs, **and**
2. A rule for **when waiting for delayed peer bids destroys feasible service** (coordination deadline / commit-now), **and**
3. Empirical evidence that this EV-specific rule changes decisions or improves the service–bytes trade-off under delay.

Without (2)–(3), ECOM certification is **not sufficiently novel** relative to AC-DMTA; the publishable asset is closer to applied RACE-COMM selective coordination on a grounded EV simulator.
