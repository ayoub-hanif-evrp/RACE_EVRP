# Stage 2 — Mathematical formulation

Benchmark: `casablanca_release_v1` · Scope: online electric parcel pickup, depot-only charging.

This formulation describes **implemented** Stage-2 / Stage-2.1 simulator semantics. It is not a claim of novelty.

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
- committed request set \(C_v\) and route plan \(\Pi_v=\Pi_v^{\mathrm{lock}}\oplus\Pi_v^{\mathrm{edit}}\)
- active leg / service lock \(\Pi_v^{\mathrm{lock}}\) (immutable while executing)
- editable suffix \(\Pi_v^{\mathrm{edit}}\) only
- mode \(\in\{\mathrm{idle},\mathrm{en\_route},\mathrm{serving},\mathrm{charging},\mathrm{emergency\_stranded}\}\)
- shift window \([\tau^{\mathrm{start}},\tau^{\mathrm{end}}]\)

Reference parameters: \(B^{\max}=40\), \(L^{\max}=600\), reserve \(B^{\mathrm{res}}=0.15 B^{\max}\), charge power \(P^{\mathrm{ch}}=22\) kW (depot only).

## 3. Dynamic requests

Request \(i\) released at \(a_i\) (not known before \(a_i\)):

- snap node \(s_i\), weight \(w_i\), service duration \(\sigma_i\)
- hard finish-by window \([e_i,\ell_i]\) (service must end by \(\ell_i\))

Lifecycle: `unreleased` → `available` → `committed` → `in_service` → `completed`, or `rejected` / `expired`.

## 4–8. Service, energy, payload, charging, shifts

Pickup at \(s_i\) starts at \(\max(\text{arrival},e_i,a_i)\) and lasts \(\sigma_i\). Payload \(L_v\leftarrow L_v+w_i\) if \(L_v+w_i\le L^{\max}\).

**Energy (Stage 2.1):** for distance \(d\) km,

- Nominal: \(E^{\mathrm{nom}}(d)=c\cdot d\) with \(c=0.2\) kWh/km  
- Conservative planning: \(E^{\mathrm{cons}}(d)=c\cdot d\cdot(1+\delta)\)  
- Realized: \(E^{\mathrm{real}}(d)=c\cdot d\cdot(1+\xi)\) with \(\xi\in[-\delta,\delta]\) via CRN key \((s,v,\mathrm{leg})\) or adversarial \(\xi=+\delta\) (synthetic; **not** measured Casablanca van data)

Feasibility is evaluated from the **projected post-lock state** (location, time, battery after the locked leg’s already-sampled realized energy, payload). A tour is energy-feasible if every editable prefix under \(E^{\mathrm{cons}}\) retains depot reachability with \(B\ge B^{\mathrm{res}}\).

**Pre-dispatch gate:** a physical departure is allowed only if the same conservative check passes for that leg. Otherwise the vehicle does not travel (planned rejection and/or `emergency_stranded`). Under \(\xi\le\delta\), a gated policy must not produce reserve breaches attributable to bound violations.

Depot return unloads all payload. Optional depot charging: \(\Delta t = \Delta B / P^{\mathrm{ch}}\) hours. No en-route chargers.

Customer **acceptance** requires finish-by \(\ell_i\) and shift end for planned service. If already `in_service` at shift end, service completes; on-time flag records whether \(\ell_i\) was met. Depot return may finish after \(\tau^{\mathrm{end}}\).

## 9. Acceptance / reassignment

- Acceptance: insert into \(\Pi_v^{\mathrm{edit}}\) only; \(\Pi_v^{\mathrm{lock}}\) immutable.  
- Reassignment: only `committed` and not locked; **atomic** (validate both sides, else restore).  
- RH commits a full fleet plan atomically or rolls back.  
- Ownership: central registry (not fully decentralized); see §11.

## 10. Objectives

Metrics: serve rate; on-time of served and of all requests; distance; energy; planned energy rejections; reserve violations; exhaustion; depot returns; charges; messages; claims; failed claims; reassignments; info age; decision runtime.

Insertion heuristics minimize added travel time subject to feasibility.

## 11. Information structure

Policies receive an **immutable observation** and a **controlled action interface** (no mutable simulator).

**Full-information:** all released tasks and all current vehicle states. No unreleased requests / future \(\xi\).

**Restricted-information:** own state, own commitments, public announcements, and peer snapshots only after message delivery. Cannot query peer true SOC/location/plans. Registry enforces claims without exposing fleet telemetry. Message delay \(\Delta^{\mathrm{msg}}\ge 0\).

## 12. Online decision process

Event-driven process with locked legs. Policies map observations to claim/insert/reassign/return/charge/idle via the action API. **No future requests, future \(\xi\), or Stage-1 witnesses.**

## 13. Centralized vs decentralized problems

- \(P_{\mathrm{full}}\): full-info online control with conservative energy gates.  
- \(P_{\mathrm{rest}}\): restricted observations + delayed messages + central ownership registry.

Clairvoyant offline solutions are evaluation oracles only, never online baselines.
