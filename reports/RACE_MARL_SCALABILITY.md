# RACE-MARL — Scalability

Compact primary matrix (frozen best F checkpoint transfer eval; not re-trained per cell):

| Factor | Settings used |
| --- | --- |
| Fleet | 3, 5 |
| Workload | Existing train/val/diagnostic scenarios (12/30/40 request regimes) |
| SOC | 35% primary |
| Delay | 0, 30 s |
| Loss | 0, 10% |

80/160-request and 10-EV cells were **not** fully executed in this compact run (generator/cost gate).

## Results

| n_vehicles | delay_s | packet_loss_p | mean_ot | mean_served | mean_sends |
| --- | --- | --- | --- | --- | --- |
| 3.000 | 0.000 | 0.000 | 0.247 | 5.667 | 10.500 |
| 3.000 | 0.000 | 0.100 | 0.247 | 5.667 | 10.500 |
| 3.000 | 30.000 | 0.000 | 0.000 | 0.000 | 1500.0 |
| 3.000 | 30.000 | 0.100 | 0.000 | 0.000 | 1500.0 |
| 5.000 | 0.000 | 0.000 | 0.268 | 6.500 | 19.167 |
| 5.000 | 0.000 | 0.100 | 0.268 | 6.500 | 19.167 |
| 5.000 | 30.000 | 0.000 | 0.000 | 0.000 | 2500.0 |

Raw: `data/casablanca/online_results/marl_scalability.csv`.
