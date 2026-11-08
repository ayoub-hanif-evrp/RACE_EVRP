# Stage 4B — Charging-and-commitment problem formulation

## Setting

Online electric parcel **pickup** on a road network with:

- One depot with charging; **no public chargers / price markets**.
- Fleet of EVs with usable battery `B_max`, reserve SOC, conservative energy uncertainty `δ`.
- Stochastic (scenario-realized) request releases with hard time windows.
- Locked active legs vs editable plan suffixes (Stage 2.1 commitment semantics).

## Decisions (online)

At each decision epoch the controller may:

1. **Commit / skip** available pickups (claim into editable plan under conservative feasibility).
2. **Depot charge** with a **discrete target SOC** from alphabet  
   `{noop, 0.50, 0.70, 1.00}` clipped to `[current_soc, 1]`.
3. Reorder editable stops (policy-dependent); locked in-transit stops are immutable.

## Hard deadlines

A pickup may enter `IN_SERVICE` only if  
`max(arrival, tw_start) + service_s ≤ tw_end`.  
Otherwise the request becomes `MISSED` (`deadline_unreachable_on_arrival`).  
**`COMPLETED` ≡ on-time.** Primary metric: **on-time completions / released requests** (`on_time_rate_all`).

## Information structure

- Full-info policies observe true fleet + available requests.
- Restricted modes retain Stage 2.1 message/ownership rules (not the Stage 4B focus).
- Offline clairvoyant upper bounds see the full request sequence a priori; online policies do not.

## Lexicographic objective

1. Maximize on-time completions among released requests.
2. Then minimize driving distance / consumed energy.
3. Then minimize compute (decision runtime).

Charge metrics for diagnostics: `energy_delivered_kwh`, `charge_duration_s`, `n_charges`.

## Offline vs online

| Object | Role |
| --- | --- |
| Tiny exact / enumerative reference | Exact optimum for a **discrete-action** charge–commitment model on ≤4 requests |
| Online policies | Same discrete charge alphabet + hard-deadline simulator; no clairvoyance |
| Gap diagnostic | Whether equalized online charge rules leave residual on-time loss vs each other / vs tiny exact |

## Out of scope (Stage 4B STOP)

No PPO/GNN/MARL; no Casablanca rebuild; no revival of Stage 3C inverse-slack or Stage 4A MC rollouts as the research claim.
