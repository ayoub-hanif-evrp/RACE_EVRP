# FINAL LOCKED RESULTS (Prompt 3)

## Execution

| Item | Value |
|---|---|
| Declared jobs | 720 |
| Completed OK | **720** |
| Failures | **0** |
| Unique `run_key` | 720 |
| Packet loss | 0% |
| Fleet / SOC | 3 EVs / 35% |
| Source SHA at run | `3e25c5458cb4799f521b63c537950eb702619084` |
| Manifest | `configs/final_locked_manifest.json` |
| Raw | `data/casablanca/online_results/final_locked/final_locked_raw.csv` |

Breakdown: delay 0 → 300; delay 30 → 210; delay 120 → 210.

## Mean on-time service (`on_time_rate_all`)

| Treatment | 0 s | 30 s | 120 s |
|---|---:|---:|---:|
| A_NONE_NOW | 0.8281 | 0.8281 | 0.8281 |
| B_FULL_COMM | 0.8342 | 0.7506 | 0.8197 |
| C_PERIODIC_COMM | 0.8342 | — | — |
| D_RANDOM_BYTE_MATCHED | 0.8356 | — | — |
| E_EVENT_TRIGGERED | 0.8342 | — | — |
| F_SELECTIVE_LEGACY | 0.8342 | 0.7508 | 0.7958 |
| G_SELECTIVE_VALID_PEER | 0.8342 | 0.7469 | 0.8197 |
| H_CSC_LITE | **0.8342** | **0.8303** | **0.8197** |
| I_MATCHED_WAIT_ZERO_COMM | 0.8281 | 0.8303 | 0.8197 |
| J_MATCHED_WAIT_MESSAGE_PLACEBO | 0.8281 | 0.8303 | 0.8197 |

## Mean attempted recipient bytes

| Treatment | 0 s | 30 s | 120 s |
|---|---:|---:|---:|
| A | 0 | 0 | 0 |
| B | 231 264 | 341 491 | 253 865 |
| C | 48 864 | — | — |
| D | 49 030 | — | — |
| E / F / G / H | 55 306 | (see below) | (see below) |
| H | 55 306 | 64 434 | 48 903 |
| I | 0 | 0 | 0 |
| J | 50 732 | 64 434 | 48 903 |

At delay 30: F≈313k, G≈308k, B≈341k. At delay 120: F≈155k; G=H=J≈48.9k.

## Safety (all locked runs)

Reserve violations = 0; battery exhaustion = 0; strandings = 0 for every treatment.

## Notes

- At zero delay, H ≡ B ≡ E ≡ F ≡ G ≡ C on mean OT (within rounding); D slightly higher (+0.14 pp vs H, CI includes 0).
- At 30 s, speculative-deferral treatments (B/F/G) collapse; H ≡ I ≡ J.
- At 120 s, H ≡ I ≡ J ≡ G ≡ B; F remains worse.

No post-hoc treatment was added after outcome inspection.
