# Suitability decision

Question. Is LaDe-P a credible primary empirical foundation for studying online decentralized electric pickup routing, given that actual electric-vehicle operations and request release times are not directly observed?

Decision. **CONDITIONALLY SUITABLE.**

The condition is narrow. The Jilin pickup file is a credible foundation for the demand, time-window, and accepted-work side of an online sequencing study. It is not a foundation for measured electric-vehicle energy, depot charging, or fleet communication. Those pieces can enter only as explicit counterfactuals. If a paper needs the data to show that real electric vehicles consumed, charged, or coordinated in a particular way, the same file is unsuitable for that claim.

## Strongest argument in favor

The file is a published industrial pickup log, and the local copy matches the published object byte for byte. It contains 261,801 unique orders, 665 couriers, and 18,880 courier-days, in line with the Jilin row of the LaDe paper. Every row has a stop, a promised window, an acceptance time, and a completion time. The business date matches the completion date on every row, so a daily duty can be reconstructed without imputing timestamps.

The duties have the structure an online pickup study needs. The median duty has 8 tasks and the mean has 13.9. On 90.1% of acceptances, at least one other accepted task is still open. Multi-task days almost all contain later acceptance minutes, with a typical within-duty gap on the order of 12 minutes, and 14.9% of tasks arrive in a same-minute batch. Windows are usable: 92.8% last exactly two hours, completion is late on only 0.20% of tasks, and 29.0% of historical completions occur before the window opens. Sampled couriers overlap on 95% of region-days. That is a real, dynamic, spatially shared pickup trace, not a synthetic request generator.

## Strongest limitation

Nothing required to identify the electric and decentralized parts of the proposed problem is measured.

Acceptance time is the courier's acceptance. The paper's own process puts customer request creation and platform dispatch before that timestamp, and neither event is stored. There is no vehicle type, battery, energy, package weight, depot, road time, or inter-vehicle message. Courier ids are a sample: 166 couriers account for 93.8% of tasks, 101 appear once, and four of the fifteen regions lie more than 50 km from the main component with almost no shared couriers. Personal accept-GPS starts are stable for the minority of couriers who have them, and they do not collapse to one depot. Any result about energy feasibility, depot-only charging, or the value of communication would be produced by the assumptions layered on top of the trace.

## Why the decision is conditional rather than a refusal

The missing electric fields were known before the audit. The audit asks whether the observed pickup process is still solid enough to carry a counterfactual study. It is, for a stated purpose: replay fixed courier-day task sets in acceptance-time order, on the observed stops and windows, and score service against those windows. The May ramp, the 21–25 June trough, the 2.94% of tasks accepted on the previous month-day, the far regions, and the one-task duties are all visible and can be held out in sensitivity checks.

The decision would become unsuitable if the empirical claim were any of the following:

- the historical operation was electric;
- simulated energy use is the couriers' energy use;
- `accept_time` is demand release;
- the 665 ids are the fleet that was available to a dispatcher;
- a communication policy's gain is a field result.

## Evidence that fixes the boundary

| Finding | Consequence for the claim |
| --- | --- |
| 261,801 unique orders, acceptance and completion on every row, completion date equal to `ds` | Daily accepted-work traces are directly supported. |
| 90.1% of acceptances see other open work; later acceptances are common | Online sequencing has something to decide inside a duty. |
| 95% of region-days contain at least two sampled couriers | A controlled information-sharing experiment has spatial overlap to act on. |
| No release time, no message log, no unsampled couriers | Decentralized information sets are designed, not observed. |
| No battery, weight, depot, or road time | Energy and charging results are scenario results. |
| Coordinates perturbed to about 10 m; 23 completion-GPS points lie more than 50 km from the stop | Stop geography is usable at neighborhood scale. Raw GPS is not a clean trajectory. |
| Year absent; November absent despite the datasheet wording; 15 regions appear rather than the 30 described in the sampling text | Do not upgrade the file into a complete dated city census. |

## What the condition allows

Use LaDe-P Jilin as the industrial demand trace. State the counterfactual the moment the text says "electric vehicle," "battery," "depot charging," "request arrival," or "message from another vehicle." Under that discipline the dataset is a credible primary empirical foundation. Without that discipline it cannot support the research claim in the working title.
