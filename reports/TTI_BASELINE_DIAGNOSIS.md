# TTI baseline diagnosis (Mon–Sat only)

Sunday held out from this diagnosis; no holdout tuning.

```json
{
  "generated_at_utc": "2026-11-07T14:52:04+00:00",
  "fit_days": [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday"
  ],
  "tti_reference_speed_kmh": 60.0,
  "workbook_free_flow": {
    "n_rows": 63360,
    "median_ff_speed_kmh": 59.999999999999886,
    "mean_ff_speed_kmh": 60.241545600573986,
    "p10_ff_speed_kmh": 58.38921842138586,
    "p90_ff_speed_kmh": 61.78279586506207
  },
  "closed_form_mon_sat": {
    "A_tti_times_d_over_60": {
      "mae_min": 0.2362237616255767,
      "signed_bias_min": 0.03368150085014255,
      "median_signed_bias_min": -1.0658141036401503e-14
    },
    "B_tti_times_d_over_30_osm_like": {
      "mae_min": 7.637363188099019,
      "signed_bias_min": 7.636960855235639,
      "median_signed_bias_min": 7.049999999999984
    },
    "interpretation": "If A tracks observations and B is systematically long, workbook TTI is relative to ~60 km/h and must not be multiplied onto slower OSM free-flow."
  },
  "path_sample": {
    "n": 80,
    "median_ratio_osm_over_tti60": 1.5095171787770165,
    "median_signed_bias_tti60_min": 0.5870532534925816,
    "median_signed_bias_osm_x_tti_min": 3.6014145333336436
  },
  "decision": "Adopt t = (3.6 * length_m / 60) * TTI for congested travel times; retain OSM topology/routing and documented class speeds for provenance only."
}
```
