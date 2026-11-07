# Stage 2 — Mathematical formulation

Benchmark: `casablanca_release_v1` · Scope: online electric parcel pickup, depot-only charging.

This formulation describes **implemented** Stage-2 simulator semantics. It is not a claim of novelty.

## 1. Network and travel times

Directed MultiDiGraph \(G=(V,E)\). Edge length \(\ell(e)\) metres. Congested travel time at clock time \(\tau\) (seconds since midnight):

\[
t(e,\tau)=\frac{3.6\,\ell(e)}{60}\cdot f\!\big(z(e),d,h(\tau)\big),
\]

with workbook TTI factor \(f\) (zone×day×hour or citywide hourly fallback) and explicit wait-for-next-hour policy when it improves arrival. Path travel time \(T(P,\tau)\) is the sum of edge durations along a fixed node path \(P\) under that policy.

**No future request or future disturbance information enters \(f\) beyond the deterministic published TTI profiles.**

## 2. Vehicles

Fleet \(\mathcal{V}=\{1,\ldots,m\}\). Vehicle \(v\) state at time \(\tau\):

- location node \(n_v\), free/busy flag, clock ready time \(r_v\)
- battery energy \(B_v\in[0,B^{\max}]\) (kWh)
- onboard payload mass \(L_v\in[0,L^{\max}]\) (kg)
- committed request set \(C_v\) and route plan \(\Pi_v\)
- shift window \([\tau^{\mathrm{start}},\tau^{\mathrm{end}}]\)

Reference parameters: \(B^{\max}=40\), \(L^{\max}=600\), reserve \(B^{\mathrm{res}}=0.15 B^{\max}\), charge power \(P^{\mathrm{ch}}=22\) kW (depot only).

## 3. Dynamic requests

Request \(i\) released at \(a_i\) (not known before \(a_i\)):

- snap node \(s_i\), weight \(w_i\), service duration \(\sigma_i\)
- hard finish-by window \([e_i,\ell_i]\) (service must end by \(\ell_i\))

Lifecycle: `unreleased` → `available` → `committed` → `in_service` → `completed`, or `rejected` / `expired`.

## 4–8. Service, energy, payload, charging, shifts

Pickup at \(s_i\) starts at \(\max(\text{arrival},e_i,a_i)\) and lasts \(\sigma_i\). Payload \(L_v\leftarrow L_v+w_i\) if \(L_v+w_i\le L^{\max}\).

**Energy (Stage 2):** for distance \(d\) km,

- Nominal planning: \(E^{\mathrm{nom}}(d)=c\cdot d\) with \(c=0.2\) kWh/km  
- Realized: \(E^{\mathrm{real}}(d)=c\cdot d\cdot(1+\xi)\), \(\xi\sim\mathrm{Uniform}[-\delta,\delta]\) (documented synthetic disturbance; **not** measured Casablanca van data)  
- Conservative planning bound: \(E^{\mathrm{cons}}(d)=c\cdot d\cdot(1+\delta)\)

A planned tour is energy-feasible if, after every prefix under \(E^{\mathrm{cons}}\), remaining energy can reach the depot and stay \(\ge B^{\mathrm{res}}\). Realized SOC uses \(E^{\mathrm{real}}\); reserve violations under realization are recorded even if planning passed.

Depot return unloads all payload. Optional depot charging: \(\Delta t = \Delta B / P^{\mathrm{ch}}\) hours, vehicle unavailable while charging. No en-route chargers.

Customer service must finish by \(\tau^{\mathrm{end}}\); depot return may finish after \(\tau^{\mathrm{end}}\).

## 9. Acceptance / reassignment

- Acceptance: assign available request \(i\) to vehicle \(v\) only if insertion into \(\Pi_v\) is feasible under time windows, payload, and conservative energy-to-depot.  
- Reassignment: only while status is `committed` and pickup has not started.  
- Cancellation / expiry: if \(\ell_i\) passes without service start/finish per policy rules.  
- Ownership: at most one vehicle holds a request (central registry in both information modes; see §11).

## 10. Objectives

Primary evaluation metrics (not a single scalar “utility” forced on all policies):

- serve rate, on-time rate, driving distance, energy consumed  
- reserve / payload violations (realized)  
- depot returns, charging events, messages, decision runtime  
- rejected / expired requests  

Secondary scalar used by insertion heuristics (documented weights): minimize added travel time subject to feasibility; reject if infeasible.

## 11. Information structure

**Full-information (centralized):** dispatcher observes all released requests and all vehicle states \((n_v,r_v,B_v,L_v,C_v)\). Does **not** observe unreleased requests or future \(\xi\).

**Restricted-information:** vehicle \(v\) observes own state, own commitments, and messages delivered by time \(\tau\). Peers’ SOC/location unknown unless messaged. Task ownership uses a minimal central registry (not fully decentralized). Message delay \(\Delta^{\mathrm{msg}}\ge 0\); each send incurs unit communication cost.

## 12. Online decision process

Event-driven MDP-like process: events are request release, vehicle arrival, service end, charge end, message delivery, shift end. At decision epochs, a policy maps observable information to accept/insert/reassign/return/charge/idle actions. **Policies must not read future requests, future \(\xi\), or Stage-1 offline witnesses.**

## 13. Centralized vs decentralized problems

- \(P_{\mathrm{full}}\): online full-info control with deterministic TTI and conservative energy for feasibility.  
- \(P_{\mathrm{rest}}\): same physics; decisions use restricted observations + delayed messages.

Clairvoyant offline solutions are **evaluation oracles only**, never online baselines.
