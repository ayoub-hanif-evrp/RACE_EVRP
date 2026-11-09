# RACE-COMM — Method and communication problem formulation

**Status:** Phase 1 (non-learning pilot target).  
**Architecture class:** hybrid decentralized bidding + centralized atomic ownership registry (not fully decentralized).  
**Negative controls retained:** Stage 3A load-count messaging; Stage 6 RACE-RH.

## 1. Online partially observed multi-agent EVRP

Agents: electric vans \(i \in \mathcal{V}\).  
Requests: pickups \(r\) released online with hard windows \([a_r, b_r]\), service, weight.  
Constraints: battery with reserve, payload, shift; depot charging only.  
Immutable active travel/service legs cannot be rewritten.

### Information partition

| Channel | Content | Notes |
| --- | --- | --- |
| Public infrastructure | Request announcements when released | Not counted as EV↔EV communication |
| Local observation | Own node, SOC, load, commitments, plan, locked leg | Always available |
| Peer messages | Delayed task-specific bids / certificates | Subject to delay, loss, expiry |
| Central registry | Atomic task ownership claim/release | Arbitration only — **not** an omniscient router |

Policies in `info_mode=restricted` must not read live peer true state from the simulator.

## 2. Compact energy-certified task bid

Each agent \(i\) evaluating request \(r\) at time \(t\) may emit:

| Field | Meaning | Computation |
| --- | --- | --- |
| `request_id`, `sender_id` | Identifiers | Local |
| `feasible` | Conservative insertion + depot-return energy OK | `check_insertion` (self only) |
| `marginal_travel_s` | Extra travel vs current plan | From feasibility check |
| `marginal_energy_kwh` | Extra driving energy | From feasibility check |
| `energy_flex_kwh` | Residual energy margin after plan | From feasibility check |
| `deadline_slack_s` | Min window slack under plan | From feasibility check |
| `charge_burden_s` | Extra depot charge time implied (0 if none) | Local estimate / 0 in v1 |
| `as_of_s`, `expires_s` | Timestamp and validity | \(t\), \(t+\tau\) |

A received bid is **advisory**. Commitment still requires a fresh self-side feasibility check and registry claim. Stale/expired bids are ignored.

## 3. Cooperative assignment rule (identical across communication modes)

For each announced request (deadline order):

1. Compute **own** bid from local state.
2. Collect non-expired peer bids for that request from the inbox/local bid table.
3. Rank feasible bids by `(marginal_travel_s ↑, −energy_flex_kwh ↑, −deadline_slack_s ↑, sender_id)`.
4. Claim iff own bid is feasible and strictly best (or tied with lexicographically smallest id = self).
5. Otherwise defer (do not claim).

**No-communication mode** uses the same rule with an empty peer-bid set → pure local feasible greedy claims, registry resolving races.

This isolates the effect of messaging from changes to the underlying dispatch logic.

## 4. Selective communication trigger

Send or refresh a bid for \(r\) only when decision-relevant, e.g.:

- New announcement and own bid is feasible; or
- Own bid fields changed beyond thresholds since last send; or
- A peer bid currently ranks better/worse such that contesting or withdrawing matters; or
- Validity of last own bid is about to expire while \(r\) remains open.

Do **not** trigger from privileged global peer truth.  
Periodic / full / random modes exist only as ablation controls under matched budgets where applicable.

## 5. Objectives and costs

- Primary service: on-time completed pickups / released pickups.
- Communication cost: messages sent and payload bytes.
- Safety: reserve violations, exhaustion, hard-deadline integrity.
- Decision quality of messages: counterfactual intended claim with vs without received bids.

Success requires a service–communication Pareto improvement (or matched-budget superiority vs random), not merely fewer messages.

## 6. Explicit non-claims

- Multi-agent bidding alone is not novel.
- Event-triggered messaging alone is not novel.
- MARL/GNN are out of scope until the non-learning protocol shows measurable communication value.
