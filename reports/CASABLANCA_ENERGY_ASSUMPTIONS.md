# Casablanca energy assumptions

All fleet energy parameters are **hypothetical scenario assumptions**, not measured Casablanca delivery-van telemetry.

## Fleet profile (`configs/fleet_default.yaml`)

| Parameter | Value | Notes |
| --- | --- | --- |
| Usable battery | 40 kWh | Labeled hypothetical light EV van |
| Payload | 600 kg | Scenario bound |
| Initial SoC | 1.0 | Full at start |
| Reserve SoC | 0.15 | Soft energy floor for witnesses |
| Consumption | 200 Wh/km | Constant urban assumption |
| Charging | Depot-only, 22 kW | No en-route charging in Stage 1 |
| Vehicles | 3 | Scenario fleet size |

## HELECAR-D

HELECAR-D reports small-EV energy behaviour for Rabat–Salé passenger contexts. It is cited only as an optional plausibility note that tens-to-low-hundreds of Wh/km are order-of-magnitude consistent for light electric vehicles. It does **not** calibrate the Stage-1 delivery-van profile.

## Witness bookkeeping

Feasible-mode witnesses deduct a fixed 2 km equivalent hop per request for constructive energy accounting. This is a certificate artifact under stated assumptions, not a claim of observed routing energy.
