# FINAL METHOD CAUSAL PILOT

**Script:** `scripts/run_race_csc_pilot.py`  
**Raw:** `data/casablanca/online_results/race_csc_pilot.csv` (246 rows)  
**Summary:** `data/casablanca/online_results/race_csc_pilot_summary.csv`  
**Paired:** `data/casablanca/online_results/race_csc_pilot_paired.json`  
**Config:** `data/casablanca/online_results/race_csc_pilot_config.json`  
**Wall time:** ~1295 s (4 workers)

## Configuration

- Scenarios: `baseline_seed{1,4}`, `peak_stress_seed{2,5}`, `tight_windows_seed{3,6}`
- 3 EVs, initial SOC 0.35, Casablanca graph + frozen traffic
- Delays: 0 / 15 / 30 / 120 s; packet-loss pilot p=0.10 at 30 s (subset of arms)
- Identical request realizations across treatments; same insertion checker & registry

## Mean on-time rate (loss = 0)

| Treatment | 0 s | 15 s | 30 s | 120 s |
|-----------|-----|------|------|-------|
| A NONE_NOW | 0.792 | 0.792 | 0.792 | 0.792 |
| B FULL | 0.801 | 0.646 | 0.668 | 0.779 |
| C SELECTIVE_LEGACY | 0.801 | 0.633 | 0.685 | 0.732 |
| D SELECTIVE_CURRENT | 0.801 | 0.633 | 0.682 | 0.779 |
| E MATCHED_WAIT_NO_PEER | 0.792 | 0.792 | 0.793 | 0.779 |
| F VALID_PEER_SELECTIVE | 0.801 | 0.633 | 0.682 | 0.779 |
| G CSC+confirm | 0.801 | 0.792 | 0.793 | 0.779 |
| H CSC no-confirm | 0.801 | 0.792 | 0.793 | 0.779 |
| I CSC no deadline wait | 0.801 | 0.792 | 0.776 | 0.779 |

## Mean bid bytes (loss = 0)

| Treatment | 0 s | 15 s | 30 s | 120 s |
|-----------|-----|------|------|-------|
| A | 0 | 0 | 0 | 0 |
| B | 213k | 375k | 322k | 229k |
| D | 55k | 159k | 209k | 48k |
| E | 50k | 62k | 63k | 48k |
| G | 100k | 106k | 107k | 91k |
| H | 55k | 62k | 63k | 48k |

## Key paired contrasts (G = full CSC candidate)

| Contrast | Delay | ΔOT (pp) | Owner Hamming | Interpretation |
|----------|-------|----------|---------------|----------------|
| G vs E | 0 | +0.97 ± 2.71 | 9.17 | Peer offers help at 0 delay |
| G vs E | 15 / 30 / 120 | 0.00 | 0.00 | Under delay, ≡ no-peer claims |
| G vs D | 15 | +15.83 ± 3.73 | 15.83 | Stops speculative deferral |
| G vs D | 30 | +11.11 ± 6.40 | 17.83 | Same |
| G vs H | all | 0.00 | 0.00 | Confirmation adds bytes only (~44 kB) |
| H vs E | 15–120 | 0.00 | 0.00 | CSC-lite ≡ matched no-peer under delay |
| H vs E | 0 | +0.97 | 9.17 | Zero-delay cooperation retained |
| Loss 0.1 @30: G vs E | 30 | 0.00 | 0.00 | Same under 10% loss |

## Safe-fallback counters (G/H)

At 15–30 s: mean `n_csc_safe_fallbacks` ≈ 4.7–4.8; `n_speculative_offers_ignored` ≈ 21–23.  
`n_counterfactual_decision_changes` under delay for G/H = **0** (offers do not change claims by design).

## Operational interpretation

1. Speculative deferral to delayed offers is the causal failure mode of selective/full under delay.
2. Commitment-safe claim restores service to the matched no-peer schedule.
3. Extra claim_intent/owned traffic does not improve ownership or OT on this pilot.
4. Zero-delay peer ranking remains valuable (~+1 pp vs none) at selective bandwidth.

## Failures / caveats

- n = 6 scenarios — development diagnosis only; not journal-ready inference.
- `total_energy_kwh` column often 0 in metrics export; distance remains informative.
- Battery reserve violations summed to 0 on this pilot.
