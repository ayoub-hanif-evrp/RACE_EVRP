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

{
  "status": "ok",
  "holdout_day": "Sunday",
  "n_test_rows": 10560,
  "mae": 0.4865195999849725,
  "rmse": 0.614118174556852,
  "median_abs_error": 0.39945233115482237
}
