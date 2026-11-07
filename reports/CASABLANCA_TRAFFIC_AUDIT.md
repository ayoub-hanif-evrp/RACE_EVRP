# Casablanca traffic workbook audit

Source: Rouky & Bousouf, Mendeley Data DOI 10.17632/8hj76bpzpv.1, CC BY 4.0.  
Retrieved: 2026-11-06T22:28:36+00:00  
SHA-256: `4778abffbe3d7791afa58069fc8a98b6e89995174d4c64401d9367221c42d17d` (verified=True)

## Worksheets

The workbook contains Summary, Table 0 coordinates, Tables 1–4 zone attributes, and Tables 5–11 daily trajectory travel times (Monday–Sunday).

## Key facts from the downloaded file

- Communes / ZIP zones: **22**
- Coordinate points: **110** (5 per commune)
- Trajectory-hour rows: **73920**
- Days: Friday, Monday, Saturday, Sunday, Thursday, Tuesday, Wednesday
- Hours: 0–23 present
- OD coordinates present on trajectories: **1.000**
- Bidirectional OD pairs observed: **1540**
- TTI median/min/max: 2.413 / 0.968 / 7.689

## What the workbook can support

- Zone-level and hour-of-day congestion factors (Travel Time Index).
- Day-of-week variation.
- OD endpoint coordinates and Waze-reported route distances/times for held-out evaluation of aggregate travel-time models.

## What the workbook cannot support

- Road-segment GPS telemetry.
- Exact Waze route polylines.
- Edge-specific traffic calibration on the OSM graph.

Origin and destination coordinates are present for each trajectory. Waze route polylines are not present, so OSM edge matching of the observed routes is not supported by this workbook alone.

## Travel-time unit interpretation

Workbook headers label travel times as minutes. Across Tue–Sun, many cells are
integers >180. Treating those as seconds (/60) produces impossible ~1.5 km/h
median speeds. Treating them as minutes×1000 (/1000) aligns distributions with
true-minute cells and yields free-flow speeds clustered at ~60 km/h (matching
the workbook TTI definition).

{
  "rule": "values>180 interpreted as minutes*1000 (Excel decimal artifacts), else minutes",
  "rejected_rule": "values>180 as seconds (/60) \u2014 yields ~1.5 km/h median speeds (invalid)",
  "share_raw_values_gt_180": 0.5705357142857143,
  "median_travel_min": 7.017,
  "median_speed_kmh": 24.92339342467921,
  "median_free_flow_speed_kmh": 59.99999999999988,
  "share_speed_5_to_120": 1.0
}

## FIFO check on citywide hourly factors

{
  "n_downward_jumps": 9,
  "fifo_without_waiting": false,
  "remedy": "wait_for_next_bucket_or_time_dependent_dijkstra",
  "examples": [
    {
      "from_hour": 4,
      "to_hour": 5,
      "f0": 2.415097042562895,
      "f1": 2.404816815724425
    },
    {
      "from_hour": 6,
      "to_hour": 7,
      "f0": 2.40557854919481,
      "f1": 2.37922705314009
    },
    {
      "from_hour": 8,
      "to_hour": 9,
      "f0": 2.443846941761775,
      "f1": 2.390282162859215
    },
    {
      "from_hour": 12,
      "to_hour": 13,
      "f0": 2.478488746844515,
      "f1": 2.4612682574026303
    },
    {
      "from_hour": 13,
      "to_hour": 14,
      "f0": 2.4612682574026303,
      "f1": 2.4212889889917797
    }
  ]
}

## Held-out day evaluation of citywide hourly TTI

TTI profile fitted on Mon–Sat and scored on Sunday (profile-level, not OD minutes):

{
  "status": "ok",
  "holdout_day": "Sunday",
  "n_test_rows": 10560,
  "mae": 0.4865195999849725,
  "rmse": 0.614118174556852,
  "median_abs_error": 0.39945233115482237
}

Operational full-week profiles remain in `tti_citywide_hour.csv`. Genuine OD
holdout predictions must use `tti_citywide_hour_fit_mon_sat.csv` (see
`scripts/validate_od_travel_times.py`).

## Genuine Sunday OD travel-time holdout (minutes)

Fit congestion on Mon–Sat only; predict Sunday OD durations on OSM free-flow
paths × citywide TTI. Manifest: `od_travel_time_validation.json`.

| Metric | Value |
| --- | --- |
| N sampled / compared | 120 / 118 |
| Snap failures | 0 |
| Collapsed OD (`o_node == d_node`) | 2 |
| MAE | 5.91 min |
| RMSE | 8.25 min |
| Median abs error | 3.99 min |
| Peak 07–10 MAE | 5.99 min |
| Median obs / pred | 6.15 / 9.72 min |

Claim: usable aggregate travel-time check after unit correction. Does **not**
claim edge calibration or identical Waze/OSM routes. Residual bias is reported
in `reports/STAGE1_FINAL_ACCEPTANCE.md` (CONDITIONAL PASS).
