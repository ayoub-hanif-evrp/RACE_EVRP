# Stage 3A — Problem and candidate mechanism

Target: *Transportation Research Part C*. Non-learning specification for a candidate contribution.

## Candidate contribution

**Risk-aware electric pickup commitments with decision-relevant information exchange.**

Question: *Can information about another EV’s energy-feasible task commitments improve online pickup acceptance enough to justify communication cost?*

## 1. Feasible commitment set

For vehicle \(v\) at decision time \(\tau\), with projected post-lock state \(\hat s_v\) (observed battery; **conservative** remaining energy on unfinished legs — no hidden \(\xi\)):

\[
\mathcal{F}_v(\tau)=\bigl\{i\in\mathcal{A}(\tau):\exists\text{ editable insertion of }i\text{ into }\Pi_v^{\mathrm{edit}}
\text{ feasible under TW, payload, }E^{\mathrm{cons}},\text{ depot reserve}\bigr\}.
\]

## 2. Opportunity cost of accepting \(i\)

Approximate (implemented heuristic):

\[
\Delta_v(i)=\tilde T_v(C_v\cup\{i\})-\tilde T_v(C_v),
\]

marginal travel time under road TTI costs, subject to \(i\in\mathcal{F}_v\). Reject if \(i\notin\mathcal{F}_v\).

## 3. Uncertainty from stale / missing peer state

Without messages, vehicle \(v\) does not know peers’ \((n_u,B_u,C_u)\). Belief \(\mathcal{B}_v\) is empty or delayed snapshots. Mis-coordination arises when \(v\) claims \(i\) that a peer with larger \(\mathcal{F}_u\) and smaller \(\Delta_u(i)\) should take — or conversely defers incorrectly.

## 4. Decision value of a message

A peer update \(m_{u\to v}\) has value if it changes \(v\)’s action:

\[
V(m)=\mathbb{E}\bigl[J(a(I_v\cup m))-J(a(I_v))\bigr],
\]

where \(a\) is the restricted dispatch rule and \(J\) is service/travel cost. Implemented non-learning trigger: send when a documented local pressure score (commitment load, battery headroom, announced-task pressure) exceeds threshold — a proxy that the update may alter peers’ \(\mathcal{F}\) ranking.

## 5. Communication penalty / budget

Each voluntary broadcast costs 1 message (+ delivery delay). Registry claims are separate and identical across communication modes. Public task announcements are held fixed.

## 6. Conservative safety

Committed work must remain feasible under \(E^{\mathrm{cons}}\) from \(\hat s_v\). Pre-dispatch gates enforce depot reserve. Guarantee is **conditional** on \(\xi\le\delta\).

## 7. Decisions without messages

Vehicles may still claim from public announcements using own state only (`comm_mode=none`). No peer SOC/location. Registry still prevents duplicate ownership.

## Distinction from prior work

| Existing line | Why not automatically our novelty |
| --- | --- |
| Robust EVRP / Han TRE 2025 | Offline/robust routing, not online message value of commitments |
| Dynamic RL EVRP / Chen TRC 2026 | Centralized learning; not EV commitment messaging |
| Warehouse MAPD + delay / Ren TRE 2026 | Not urban EV energy commitments |
| Periodic / event-triggered control | We require **decision-value linkage to energy-feasible claims**, not timer or consensus triggers alone |
| MARL + transformers | Architecture ≠ contribution |

Novelty, if any, is the **coupling of energy-feasible commitment sets with an explicit send rule based on estimated change in peer dispatch**, evaluated against the **same** restricted claim rule under none / periodic / triggered messaging.
