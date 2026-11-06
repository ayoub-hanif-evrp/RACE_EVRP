# Dataset audit: LaDe-P Jilin pickup

Audit of the pinned file `data/raw/pickup_jl-00000-of-00001-9b430a56a935f284.parquet`. Every count below was computed from that file after the schema check. Derived fields are labeled as derived. The numerical record is `data/processed/audit_summary.json`.

Runtime: Python 3.12.10, pandas 3.1.1, pyarrow 26.0.1, NumPy 2.5.4, Matplotlib 3.11.2.

## Schema, inspected before processing

The Arrow schema has 19 columns and 261,801 rows in one file with 262 row groups. Processing aborts if the column list differs from this order.

| Column | Arrow type | Role in the published table |
| --- | --- | --- |
| `order_id` | int64 | Package identifier. The paper's field list calls this `package_id`. The parquet column is `order_id`. |
| `region_id` | int64 | Region identifier |
| `city` | string | City name |
| `courier_id` | int64 | Anonymized courier identifier |
| `accept_time` | string | Time the courier accepts the task |
| `time_window_start` | string | Start of the required pickup window |
| `time_window_end` | string | End of the required pickup window |
| `lng`, `lat` | double | Stop coordinates from the publisher's geocoder |
| `aoi_id` | int64 | Area-of-interest identifier |
| `aoi_type` | int64 | Area-of-interest category code. The code book is not in the file. |
| `pickup_time` | string | Time the courier completes the pickup |
| `pickup_gps_time`, `pickup_gps_lng`, `pickup_gps_lat` | string / double | GPS sample associated with completion. Nullable. |
| `accept_gps_time`, `accept_gps_lng`, `accept_gps_lat` | string / double | GPS sample associated with acceptance. Nullable. |
| `ds` | int64 | Business date of the pickup, encoded as `month * 100 + day` |

Clock strings use `MM-DD HH:MM:SS`. Every non-missing clock in this file parsed, and every parsed second component is `00`. The time resolution is one minute.

`ds` runs from 501 to 1031. That encoding is 1 May through 31 October. All 184 month-days in that span occur at least once. There is no year column. Interval arithmetic in the code uses year 2001 only as an internal ordering device. That year is not a collection year, and the figures do not print it.

## Population

| Quantity | Value |
| --- | --- |
| Pickup tasks | 261,801 |
| Distinct `order_id` | 261,801 |
| Duplicate order ids | 0 |
| Exact duplicate rows | 0 |
| City values | `Jilin` only |
| Couriers | 665 |
| Regions | 15 |
| AOIs | 1,011 |
| AOI type codes | 14 |
| Business dates with at least one task | 184 |
| Calendar days in the May–October span with no task | 0 |
| Courier-days, grouped by (`courier_id`, `ds`) | 18,880 |

These headline counts agree with the paper's Jilin pickup row: 665 couriers, 261k packages, and 13.8 packages per courier-day. The mean in this file is 13.87 tasks per courier-day.

The paper also reports about 18k trajectories and 399k GPS points for Jilin pickup. This table has 18,880 courier-days. Non-missing accept-GPS and pickup-GPS fields sum to 399,717. Those two published round numbers are consistent with courier-days and event-GPS rows. They are not a separate trajectory table inside this file.

## Directly observed, derived, missing, and assumed

| Class | Variable | Evidence in this file |
| --- | --- | --- |
| A. Observed | Order identifier, courier identifier, city, region, AOI, AOI type code | Present on every row. Identifiers are anonymized. AOI type codes have no names. |
| A. Observed | Stop longitude and latitude | Present on every row. Zero coordinates fail a finite WGS84 check. The paper states that coordinates were perturbed to about 10 m. |
| A. Observed | Acceptance time | Present on every row. The publisher defines it as the time the courier accepts the task. |
| A. Observed | Promised window start and end | Present on every row. |
| A. Observed | Pickup-completion time | Present on every row. The publisher defines it as the time the courier picks up the task. |
| A. Observed | Business date `ds` | Present on every row as a month-day code. It matches the month-day of `pickup_time` on every row. |
| A. Observed, incomplete | Accept GPS time and coordinates | Missing on 81,832 rows (31.3%). |
| A. Observed, incomplete | Pickup GPS time and coordinates | Missing on 42,053 rows (16.1%). |
| B. Derived | Window length | End minus start. 92.8% are exactly 120 minutes. 6.9% are exactly 899 minutes. 640 windows have another positive length. |
| B. Derived | Acceptance-to-completion interval | Completion minus acceptance. Median 92 minutes, mean 172.1 minutes. |
| B. Derived | Courier-day task set | Grouping by courier and `ds`. This is a reconstruction rule, because `ds` follows the pickup date. |
| B. Derived | Open work at an acceptance | Count of tasks already accepted and not yet picked up. |
| B. Derived | Distances between coordinates | Great-circle distances. They are not road distances. |
| B. Derived | Hour-of-day and same-minute batches | Taken from the minute-resolution clocks. |
| C. Missing | Customer request creation / release time | No column. Acceptance is a later platform event. |
| C. Missing | Calendar year and weekday | No year is stored. A weekday cannot be recovered from the file. |
| C. Missing | Depot location and return-to-depot time | Described in the paper's process narrative. Absent here. |
| C. Missing | Package weight, volume, service duration | Absent. |
| C. Missing | Vehicle type, driving mode, battery, state of charge, energy use, charger | Absent. Rows identify couriers, not electric vehicles. |
| C. Missing | Road class, path, and road travel time | Absent from this parquet. A different LaDe repository describes road files; they were not part of this download. |
| C. Missing | Offers, rejections, dispatcher decisions, and messages between couriers | The courier id is the realized acceptor. The assignment policy is absent. |
| C. Missing | The couriers who were not sampled | The paper describes a regional sample. Fifteen region ids appear, against the paper's description of 30 selected regions. |
| D. Requires an explicit assumption | Request-arrival process | Either treat `accept_time` as the information arrival, and say so, or simulate an earlier release time. |
| D. Requires an explicit assumption | Depot and depot-only charging | A coordinate, a battery, and a charging rule would be chosen by the modeler. |
| D. Requires an explicit assumption | Energy consumption and travel time | Any energy or road-time number would come from an external model. |
| D. Requires an explicit assumption | What one vehicle knows about other vehicles | The file is an ex-post sample. It contains no communication log. |
| D. Requires an explicit assumption | Which historical courier is one vehicle | Courier ids are unevenly observed. Equating an id with an electric vehicle is a modeling choice. |

## Time

Acceptance is concentrated early. Hours 07:00 and 08:00 contain 76,521 and 71,023 acceptances, together 56.4% of tasks. A second, lower band runs from late morning through 16:00. Only 269 acceptances fall at hour 17 or later, and 4 fall at hour 00.

Completion peaks later: 49,486 pickups in hour 09 and 41,453 in hour 10. Completions continue through hour 17 (16,144) and then fall. A handful of completion clocks fall at hours 00, 04, 05, or 23.

| Timing fact | Result |
| --- | --- |
| Acceptance before the window opens | 85.1% of tasks |
| Acceptance after the window closes | 2 tasks |
| Completion inside the window | 70.8% |
| Completion before the window opens | 29.0% |
| Completion after the window closes | 0.20% (514 tasks) |
| Completion before acceptance | 0 |
| Acceptance month-day equals `ds` | 97.06% |
| Completion month-day equals `ds` | 100% |
| Acceptance and completion on different month-days | 2.94% |
| Window crosses a calendar date | 90 tasks (0.034%) |
| December-to-January wrap on the placeholder year | 0 |

The cross-date cases are ordinary next-day pairs already written into the strings, such as a window that starts on one month-day and ends on the next. Because both month-days are stored, those intervals can be ordered without a year. A full civil date still cannot be reconstructed, because the year is absent and the datasheet's phrase "a recent year" does not identify one. The datasheet's mention of November is also absent from `ds`: the last code is 31 October.

Where an accept-GPS time exists, it is at the acceptance minute or up to 10 minutes earlier, and it is never later. Pickup-GPS times have the same pattern. The released GPS time behaves as the latest sample at or before the event inside a 10-minute lookback, with the field left empty otherwise. The paper's phrase "closest GPS point" is broader than what this file retains.

Acceptance-to-completion has a long right tail. The median is 92 minutes, the 90th percentile is 361 minutes, 3.0% exceed 12 hours, and 1.9% exceed 24 hours. The maximum is 8,599 minutes. The paper's Jilin "AvgETA" of 123 minutes uses a query-time definition whose columns are not in this file, so that published average was not recomputed.

Same-minute structure matters for online decisions. Within a courier-day, 14.9% of tasks share their acceptance minute with another task of that duty. Every one of the 13,490 multi-task duties has a positive gap between completion times. Of those, 13,465 also have a positive gap between acceptance times. The median of those within-duty median acceptance gaps is 12.5 minutes. The other 25 multi-task duties accept the whole set in one minute. Staggered arrivals and small batches both occur. Order inside a shared minute is not observed.

## Courier-days

Grouping by courier and `ds` is justified by the perfect match between `ds` and the completion date. It places an acceptance that happened on the previous month-day into the completion day's duty. That affects 2.94% of tasks. The resulting duty can therefore start before the business date.

| Courier-day statistic | Value |
| --- | --- |
| Duties | 18,880 |
| Tasks per duty: minimum, 25th percentile, median, mean, 75th, 90th, maximum | 1, 1, 8, 13.87, 24, 35, 72 |
| Duties with one task | 5,390 (28.5% of duties, 2.1% of tasks) |
| Duties in which some acceptance occurs while another accepted task is still open | 66.8% |
| Share of acceptances that see at least one other open task | 90.1% |
| Maximum open tasks at an acceptance | 43 |
| Median duty span, last completion minus first acceptance | 560 minutes |
| Active couriers per date: minimum, median, maximum | 1, 102, 163 |
| Tasks per date: minimum, median, maximum | 18, 1,526, 2,248 |

The courier panel is unbalanced. Median tasks per courier over the whole file are 17, and the median courier is active on 13 dates. One hundred one couriers appear on a single date and account for 0.099% of tasks. One hundred sixty-six couriers active on at least 30 dates account for 93.8% of tasks. One courier-day of a rarely seen id is a weak stand-in for a vehicle that operates every day.

Daily volume rises through early May, from 18 tasks on 1 May to several hundred by mid-May, then sits mostly between about 1,200 and 2,200 tasks. The peak is 2,248 tasks on 7 June. Codes 621 through 625 (21–25 June) fall to 403–443 tasks. Those dates are present; they are a trough, not a hole. Without a year, this audit does not attribute the trough to a holiday.

Figure: `figures/fig1_daily_pickup_volumes.pdf`. Figure: `figures/fig2_tasks_per_courier_day.pdf`.

## Geography

The median stop is 126.56860 E, 43.82347 N. All 261,801 stop coordinates pass a finite WGS84 check and none sit at (0, 0). There are 228,980 distinct stop coordinates. Repeated coordinates hold 21.4% of tasks, and the busiest coordinate has 27 tasks. The paper's 10 m perturbation still applies, so coordinates finer than that accuracy are not exact customer locations.

The stops do not form one compact city square.

| Component | Tasks | Couriers only in that component |
| --- | --- | --- |
| Within 20 km of the median stop | 207,610 (79.3%) | — |
| More than 50 km from the median stop | 54,181 (20.7%) | 175 |
| Within 50 km, which adds only 10 tasks to the 20 km set | 207,620 | 484 |

Six couriers appear in both components. The far tasks belong entirely to region ids 9, 11, 114, and 132. The near tasks belong to the other eleven regions: 13, 29, 74, 85, 90, 91, 109, 110, 122, 128, and 131. Latitude separates the far mass further: 32,490 stops are south of 43.2 N, and 8,973 are north of 44.2 N. Two stops have longitude above 128 and fall outside the central 99% window drawn in the map.

The paper's Table 2 lists a 20 km by 20 km spatial span for Jilin pickup. That description fits the main component only as a rough scale. It does not cover the four far regions in this file.

AOI type code 1 accounts for 153,685 tasks (58.7%) and code 14 for 95,590 (36.5%). The paper's statement that type 1 exceeds 70% is a Shanghai figure and does not describe Jilin. The largest AOI holds 2.5% of tasks. The top ten AOIs hold 15.0%. The Herfindahl index across 1,011 AOIs is 0.0049, so tasks are spread across many AOIs even though the map is locally dense. The densest approximately 1 km grid cell holds 8,670 tasks (3.3%). The ten densest cells hold 27.1%.

On 95.0% of region-days at least two sampled couriers are present (maximum 30). On 15.2% of AOI-days at least two couriers are present, and those shared AOI-days contain 32.1% of tasks (maximum 9 couriers). Sampled couriers therefore overlap in space. The overlap is much stronger at region level than at AOI level.

Accept GPS, when present, is typically hundreds of meters from the stop: median 537 m, 90th percentile 1.54 km. Pickup GPS is closer: median 68 m, 90th percentile 452 m. Extreme GPS remains. Twenty-six accept-GPS points and 23 pickup-GPS points are more than 50 km from their stop, and 520 pickup-GPS points are more than 5 km away. The farthest pickup-GPS point is about 1,483 km from its stop. Those points are anomalies in the GPS fields. They are not usable as travel distances.

Figure: `figures/fig3_geographic_distribution.pdf`.

## A stable start point is not a measured depot

For 145 couriers with at least five duties that have an accept-GPS at the earliest acceptance, the courier's own start points lie close together. The median of those within-courier median offsets is 53 m, and 85.5% are within 500 m. Across couriers, those personal median starts are dispersed. Their median distance from the median personal start is 5.6 km, and only 11.1% lie within 2 km of that center. The 90th percentile is 106 km because personal starts also occur in the far regions.

A regularly observed courier often begins the recorded day near a personal location. Those locations are not one shared depot, the GPS is missing for many duties, and the field is an acceptance position rather than a labeled depot departure.

## What the event log can reconstruct

A courier-day can be rebuilt as an ordered set of minute-stamped events:

1. The business date is the pickup date.
2. Each task has a stop, a window, an acceptance time, and a completion time.
3. At an acceptance minute, the tasks accepted at or before that minute and not yet completed are the courier's known open work.
4. On 90.1% of acceptances that set contains at least one other task.
5. New acceptance minutes continue through the duty. The typical positive gap is on the order of 10–30 minutes, with a heavy tail.

This supports an asynchronous event trace of work that the courier has already accepted. It does not recover the moment the customer created the request, the moment the platform offered it, or any offer the courier did not accept. The paper itself separates those steps: the customer places an order, the platform dispatches it, and the courier accepts it. Only the third step is timestamped here.

The observed couriers are not labeled as electric vehicles, vans, motorcycles, or e-bikes. Battery state, payload, and energy are not observed, so an electric-vehicle interpretation cannot be read out of the table. It can only be imposed later as a counterfactual.

Figures for windows and event times: `figures/fig4_time_windows.pdf` and `figures/fig5_acceptance_and_completion.pdf`.
