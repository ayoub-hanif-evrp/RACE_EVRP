# Constraint binding diagnosis (existing certified baselines)

Fleet usable battery 40.0 kWh, reserve 6.0 kWh, payload 600.0 kg.

Certified baselines analyzed: **5**.

| Scenario | Min battery (kWh) | Headroom vs reserve | Max load (kg) | Payload headroom |
| --- | ---: | ---: | ---: | ---: |
| train/baseline_seed1 | 26.944871228495664 | 20.944871228495664 | 106.58819484785353 | 493.4118051521465 |
| train/baseline_seed4 | 25.36099695709743 | 19.36099695709743 | 109.81186680429512 | 490.1881331957049 |
| train/baseline_seed42 | 27.932118699113396 | 21.932118699113396 | 90.67248972475711 | 509.3275102752429 |
| train/baseline_seed7 | 26.20482602743009 | 20.20482602743009 | 103.88512064436443 | 496.1148793556356 |
| test/baseline_seed202 | 23.044607605706716 | 17.044607605706716 | 114.12355940107203 | 485.87644059892796 |

Energy binds (<1 kWh headroom): **False**. Payload binds (<10 kg headroom): **False**.

Offline constructive witnesses with full request visibility. Comfortable residual battery/payload on baselines does not prove energy-risk coordination is a hard online problem; it only shows current baseline regimes are not energy- or payload-binding.
