# Stage 1.5 handoff — Scientific data integrity freeze

Date: 2026-11-07  
Benchmark: **`casablanca_stage1_5_v1`**  
Stop: no Stage-2 algorithms (no PPO/GNN/simulator).

## Fixed

| Finding | Status |
| --- | --- |
| Workbook vs HCP population overwrite / wrong demand input | **Fixed** — separate sources + `demand_zone_weights.csv` only |
| Silent citywide candidate fallback | **Fixed** — fail / renormalize eligible zones |
| Wrong pickup location accepted by validator | **Fixed** — `wrong_customer_node` |
| Midnight vehicle start vs 08:00 operations | **Fixed** — `shift_start_s` / service `shift_end_s` |
| Al Idrissia / Sidi Maarouf bad admin polygons | **Fixed** — OD-hull approximate study zones |
| CRLF vs LF checksum pin | **Fixed** — `.gitattributes` LF + regenerated pins |
| Absolute Windows paths in new pins | **Fixed** — relative paths |
| Stale demand counts in docs | **Updated** in freeze/handoff reports |

## Unresolved / limitations

- Energy and payload still **do not bind** on certified baselines (~17–24 kWh headroom).
- Traffic model is an improved approximation, not high-fidelity edge reconstruction.
- 7 approximate study zones remain without official admin polygons (by design).
- 5 zones have zero accessible SCC candidates and are excluded from sampling.
- Online multi-agent decision environment still not implemented (out of scope).

## Can the benchmark be frozen?

**Engineering freeze: YES** for `casablanca_stage1_5_v1` as a reproducible Casablanca dataset + certificate stack under the documented assumptions.

**Scientific freeze for top-tier method claims: NO** until a nontrivial EVRP decision problem is defined where energy/communication risk actually binds.

## Tests actually run

```text
36 passed
```

Includes feasibility adversarial suite (wrong customer node, shift start, fleet IDs, prior cases) and boundary checksum verification.

## Demonstrated baseline

`train/baseline_seed1`: independently certified under shift-aware validator; spatial weights from `demand_zone_weights.csv`; generator `0.3.0`.

## Next intellectual step (not this stage)

Define the precise transportation decision problem (dynamic acceptance, energy uncertainty, information asymmetry) **before** implementing RACE multi-agent learning.
