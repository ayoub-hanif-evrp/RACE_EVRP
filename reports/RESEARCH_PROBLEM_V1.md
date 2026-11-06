# Research specification, version 1

Status: a candidate problem constrained by the Jilin LaDe-P audit. This is not a claim of theoretical novelty, and it is not an implemented model.

The working title remains "Reliable Decentralized Electric Pickup Routing under Energy Uncertainty and Incomplete Fleet Information." Stage 1 narrows what that title can mean if LaDe-P Jilin is the empirical base.

## Operational system under study

The empirical object is the Jilin pickup partition: 261,801 completed pickup tasks, 665 anonymized couriers, 15 regions, and every month-day from 1 May through 31 October of an unidentified year.

The system we would study is a counterfactual electric pickup service faced with these observed stops, windows, and courier-day workloads. Each regularly observed courier-day is a candidate vehicle duty. The historical couriers remain couriers in the data. Calling one of them an electric vehicle is a scenario choice made after the audit, not a measurement.

Two geographic regimes are available and should not be mixed without a statement:

- The main component, eleven regions and 207,620 tasks within 50 km of the median stop.
- The full file, which also contains 54,181 tasks in regions 9, 11, 114, and 132, more than 50 km away, served by an almost disjoint set of couriers.

The service the paper describes, and that this specification adopts as the operational story, is pickup from sender locations followed by a return to a depot. The return itself is not in the table.

## Decisions a vehicle would make

Under a fixed historical assignment, each vehicle would decide, at an event time:

- which known open pickup to serve next;
- whether to insert a newly accepted task into the remaining sequence;
- whether to wait;
- when to travel back to the assumed depot and charge.

The dataset already records who accepted each task. Reassigning a task from one courier id to another would be a second, stronger counterfactual. It would replace the observed assignment rather than resequence it. The file contains no rejected offers and no dispatcher log against which a new assignment could be checked. The defensible first study holds the courier-day task set fixed and changes only the sequence, the charging returns, and the information available when the sequence is updated.

## Information a vehicle would observe

At an acceptance minute, the trace supports this information set for that courier:

- the courier's own tasks accepted at or before that minute and not yet completed;
- those tasks' stop coordinates, AOI ids, region ids, and promised windows;
- the courier's own completion history earlier in the duty;
- a position only when an accept-GPS or pickup-GPS field is present.

That position is sparse. Accept GPS is missing on 31.3% of tasks and pickup GPS on 16.1%. When present, the GPS time is at or up to 10 minutes before the event. Acceptance GPS is typically about half a kilometer from the stop. Completion GPS is typically about 70 m from the stop, with a small number of points tens or hundreds of kilometers away that cannot be used as positions.

The following information is absent and would have to be declared if a model used it:

- the customer request time and any platform offer time earlier than acceptance;
- other couriers' current tasks, positions, or intentions;
- a complete fleet roster (166 of 665 couriers account for 93.8% of tasks; 101 appear on only one date);
- road state, battery state, and depot occupancy.

On 90.1% of acceptances the courier already holds at least one other unfinished accepted task, and the maximum such open set is 43 tasks. The decision is usually a sequencing decision over a live set, not a single-task trip. On 14.9% of tasks the acceptance minute is shared with another task of the same duty, so the trace does not order those tasks inside the minute.

## Uncertainty worth modeling

The uncertainty that the timestamps can actually discipline is future acceptance within a courier-day. Positive gaps between acceptance times are the usual pattern on multi-task days, and the median of within-duty median gaps is 12.5 minutes. A policy can be rolled forward through the observed acceptance minutes and scored on the tasks that were not yet accepted.

Energy uncertainty is not disciplined by this file. A consumption law, a battery, and a noise model would be assumptions. They can be studied as sensitivity cases. They cannot be calibrated to observed state of charge, because no such series exists.

Travel-time uncertainty is in the same class. The acceptance-to-completion interval (median 92 minutes, mean 172 minutes) mixes travel, waiting, service, and any unobserved stops. It is a human outcome under the historical sequence. It is not a link travel time.

Request-release uncertainty is also unidentified. Using `accept_time` as the release time attributes platform information to the vehicle at the moment of acceptance. Simulating an earlier release would invent times the file does not contain. Either choice has to be labeled as a convention.

## Why coordination could matter

Sampled couriers already share space. Two or more couriers appear on 95% of region-days, and on 15% of AOI-days. The shared AOI-days contain 32% of tasks. A vehicle that sequences only its own accepted work ignores that nearby accepted work belongs to someone else. Whether sharing those sets would have changed completions is not something the historical log can prove, because the log is the result of the historical assignment and because unsampled couriers are invisible.

Coordination is therefore a counterfactual experiment on top of the trace: hold the observed tasks fixed, vary how much of the other sampled vehicles' accepted work is visible, and compare service and energy under an explicit travel and energy model. The result would be evidence about that experiment. It would not be evidence that Cainiao's couriers lacked, or used, a particular communication channel.

## Depot-only charging

Depot-only charging would mean that a vehicle leaves an assumed depot with a finite battery, serves pickups, and can recover energy only by returning there. The audit supplies no depot.

The closest empirical hint is the accept-GPS at the first acceptance of a duty. For 145 couriers with at least five such points, each courier's own starts are tight, about 50 m at the median, while different couriers start kilometers apart. That pattern is consistent with personal origins. It is not a map of depots, it covers a minority of courier ids, and the GPS is an acceptance position rather than a departure from a charger.

A later implementation therefore has to choose one of these declared options:

- one synthetic depot per geographic component;
- one synthetic depot per courier, placed at that courier's median start when enough GPS exists, with a fallback rule when it does not;
- a depot taken from an external map, which would be new data and would need its own provenance.

Charging power, battery capacity, and the energy to reach the depot would be parameters. None of them can be validated against this table.

## What has to be simulated

- The identification of a courier-day with an electric vehicle, including which sparse courier ids are excluded.
- The information convention for release time.
- A travel-time function. Great-circle distance is available as a descriptive statistic and is not a road time. A road network was not part of this download.
- An energy function and a battery.
- A depot coordinate and a depot-only charging rule.
- A tie break inside a shared acceptance minute.
- Any message a vehicle receives about another vehicle.
- The couriers and requests that the sampling design left out. They cannot be reconstructed from these rows.

## What can be evaluated with this dataset

- Whether a sequencing rule, rolled through the observed acceptance times of a fixed courier-day, respects the promised windows on the observed stops.
- How often the historical completion fell inside, before, or after the window, as a human reference outcome (70.8% inside, 29.0% before, 0.20% after). Early historical completion is part of that reference. A hard window constraint would treat the early share differently from the late share, and the specification has to say which comparison it is making.
- Workload, batch size, open-set size, and spatial overlap, as scenario descriptors.
- Sensitivity of those service outcomes to the release-time convention, the geographic component, the May ramp, and the 21–25 June trough.
- Sensitivity of simulated energy and charging returns to battery and consumption parameters. Those curves would be model sensitivity, reported as such.

## What cannot be claimed as real-world evidence

- That the historical fleet was electric, or that a simulated battery would have been feasible for these couriers.
- That `accept_time` is the customer request time.
- That a simulated communication policy was used, or would have been accepted, by the platform.
- That a reassignment improves on the real dispatcher. The real assignment policy is not observed, and the fleet sample is incomplete.
- That great-circle travel or an external road time matches the couriers' travel.
- That one depot served these duties.
- A calendar weekday effect, a holiday explanation for 21–25 June, or a specific year.
- City-wide Jilin demand. The file is a regional courier sample, with 15 observed regions.

## Recommended empirical claim, if the project continues

LaDe-P Jilin can anchor the demand side of an online pickup-sequencing study: real stops, real windows, real courier-day sets, and real acceptance and completion times. Electric energy, depot charging, and decentralized communication can be attached only as declared counterfactuals. Papers written from that design can claim that a policy was tested on an industrial pickup trace under stated assumptions. They cannot claim that the trace validates electric-vehicle operations.
