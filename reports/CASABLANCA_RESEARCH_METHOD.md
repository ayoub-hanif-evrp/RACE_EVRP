# Casablanca Stage-1 research method

## Problem setting

Stage 1 constructs a reproducible Casablanca benchmark for **online electric parcel pickup with depot-only charging**. No routing/learning algorithms (PPO, GNN, event-driven EVRP simulator) are included.

## Spatial definition

Let \(\mathcal{Z}=\{z_1,\ldots,z_{22}\}\) be the workbook commune names. Each \(z\) is matched to an OSM administrative polygon \(P(z)\) when a high-confidence name match exists; otherwise a buffered convex hull of workbook OD coordinates \(H(z)\) is used and labeled as a geometric fallback. The study area is

\[
\mathcal{A}=\bigcup_{z\in\mathcal{Z}} \tilde{P}(z),\quad \tilde{P}(z)\in\{P(z),H(z)\}.
\]

This is not an arbitrary rectangle and not the full Casablanca–Settat region.

## Road graph and free-flow times

A directed drive graph \(G=(V,E)\) is extracted for \(\mathcal{A}\). Edge length \(\ell(e)\) comes from OSM geometry. Free-flow speed \(v(e)\) uses OSM `maxspeed` or class fallback \(v_{\mathrm{class}}(e)\). Free-flow travel time:

\[
t_0(e)=\frac{3.6\,\ell(e)}{v(e)}.
\]

## Congestion model

From the Waze-derived workbook, empirical Travel Time Index factors \(f(z,d,h)\) are estimated by commune, weekday, and hour. Edge travel time at departure \(\tau\) uses the zone of \(e\) when available:

\[
t(e,\tau)=t_0(e)\cdot f\big(z(e),d,h(\tau)\big),
\]

with citywide hourly \(f_{\mathrm{city}}(h)\) as fallback. This is a **multiplicative zonal/hourly model**, not edge-calibrated twinning. When piecewise-constant factors would violate FIFO, the travel-time API waits until the next hour bucket if that improves arrival.

## Synthetic demand

Accessible OSM candidates \(C\subset\mathcal{A}\) are snapped to \(G\). Requests are sampled with zone weights

\[
w(z)=\alpha\,\hat{p}(z)+\beta\,\hat{c}(z),
\]

where \(\hat{p}\) is HCP population (or documented household-scaled placeholder) and \(\hat{c}\) is workbook commercial intensity. Arrival minutes follow a declared hourly intensity profile (NHPP-style). All request fields carry `is_observed_order=false`.

## Observed vs modeled

| Quantity | Status |
| --- | --- |
| Workbook TTI by zone/day/hour | Observed (published Waze-derived) |
| OD endpoint coordinates in workbook | Observed |
| Waze route polylines / edge matching | Not available |
| OSM road geometry and lengths | Observed map data |
| Pickup request locations/times/weights | Modeled (synthetic) |
| Depot location | Modeled (OSM-derived scenario point) |
| EV battery, Wh/km, depot charging | Modeled (hypothetical) |
| Feasible witness schedules | Constructive certificates under assumptions |

## Stop line

Stage 1 ends at dataset, network, scenario generator, validation, and documentation. Algorithmic EVRP solution methods are deferred.
