# RACE-MARL Stage 8.2 — Communication Ablations

## Clean isolation matrix

| ID | Routing | Communication control | Message content | Own battery |
|----|---------|----------------------|-----------------|-------------|
| A | learned | disabled | — | yes |
| B | learned | forced full (not learned) | travel + energy | yes |
| C | learned | external random @ predeclared `matched_send_p=0.307` | travel + energy | yes |
| D | learned | learned selective (any feasible) | travel + energy | yes |
| E | learned | learned selective | peer energy stripped | yes |
| F | learned | contest/energy-cert gated selective | energy certificate tagged | yes |

## Service-versus-byte curve

Primary table: `data/casablanca/online_results/stage82_service_vs_bytes_full.csv`.

### Non-learning (validation mean)

| Method | OT | Bid bytes | Messages |
|--------|-----|-----------|----------|
| greedy_charge70 | 0.819 | 0 | 0 |
| nl_none | 0.821 | 0 | 0 |
| nl_selective | **0.832** | **47 873** | 129 |
| nl_full | 0.832 | 218 588 | 643 |
| nl_selective@30s | 0.801 | 46 968 | 127 |

Selective matches full OT at ~4.6× lower byte traffic than full.

### Learned recovery (3-seed validation mean)

| Method | OT | Bid bytes | Messages |
|--------|-----|-----------|----------|
| A_no_comm | 0.493 | 0 | 0 |
| C_random_matched | 0.493 | 7 860 | 21 |
| F_race_marl | 0.489 | 8 340 | 19 |
| B_full_comm | 0.488 | 19 776 | 53 |

F uses far fewer bytes than B and is roughly matched to C, but **OT does not improve** over A/C at this recovery budget. Gate 3 empirical communication *value* for the learned policy remains unproven.

## Matched budget

`stage82_matched_send_p.json`: `0.3074` from cooperative selective teacher send rate (predeclared, not post-hoc per test scenario).
