# FINAL OPERATIONAL RESULTS (Prompt 3)

## Energy and charging (means)

### Delay 0

| Treatment | Energy kWh | Charge delivered kWh | n_charges | Distance m | Mean decision ms |
|---|---:|---:|---:|---:|---:|
| A / I / J | 35.96 | 77.96 | 8.20 | 179 813 | ~129–136 |
| B / C / E / F / G / H | 35.09 | 77.09 | 8.07 | 175 462 | ~74–133 |
| D | 35.99 | 77.99 | 8.27 | 179 946 | ~132 |

Selective/full/CSC family travel slightly less and consume slightly less energy than no-comm at zero delay; differences are small relative to service variation.

### Delay 30 (selected)

| Treatment | Energy kWh | n_charges | Distance m | Mean ms |
|---|---:|---:|---:|---:|
| H / I / J | 35.93 | 8.30 | 179 657 | ~85–87 |
| G | 32.36 | 7.00 | 161 807 | ~102 |
| F | 31.75 | 6.90 | 158 758 | ~101 |
| B | 32.15 | 6.87 | 160 733 | ~96 |

Speculative-deferral collapse reduces completed work and thus energy/distance — not an efficiency gain.

### Delay 120

H/I/J/G/B ≈ 35.50 kWh, 8.1 charges; F lower (34.12 kWh) with worse service.

## Safety

Across all 720 locked runs: **0** reserve violations, **0** exhaustions, **0** strandings.

## Claims / coordination (H totals across delays)

- Claims attempted = claims success = 1979 (no failed claims in aggregate counter)
- Assign deferrals = 1640; defers-to-peer = 238
- A has 0 assign deferrals / 0 peer defers (immediate claim path)

## Computation

Mean decision runtime is ~70–140 ms depending on treatment/delay. Periodic is faster on average at delay 0 (~74 ms) due to fewer decision-triggered broadcasts. Wall-clock experiment time is recorded in `locked_run.log` (distinct from simulated shift time).

## Operational conclusion

No large energy or runtime advantage for CSC-lite beyond the communication-efficiency and delay-safety findings. Figure 6 documents energy parity among zero-delay competitive methods.
