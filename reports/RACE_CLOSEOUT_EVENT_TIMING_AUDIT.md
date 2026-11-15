# Event Timing & Communication Causality Audit

**Code fixes:** `race_cooperative.py` (`expects_delayed_peer_bids`, `fair_physical_decisions`), `task_bids.py` (deadline-energy wait).  
**Trace artifact:** `data/casablanca/online_results/race_closeout_event_timing_trace.csv`  
**Historical confound (pre-fix):** PASS1 / prior-devval where `none` waited `1.25×message_delay` despite sending no bids.

## Defects found

1. **No-communication waited for nonexistent peers.**  
   `assignment_wait_s(message_delay_s=…)` ran for every two-phase policy, including `comm_mode=none`. At 30 s delay this scheduled ~37.5 s assign waits with nothing to receive.

2. **Periodic waited similarly** even though it only transmits on timer ticks, not on `bid_exchange`.

3. **Message / periodic ticks granted extra physical decisions** (claim + charge) beyond shared release/idle/charge-end opportunities, confounding communication with opportunity count.

## Corrections

| Fix | Behavior |
|-----|----------|
| `expects_delayed_peer_bids()` | `none` and `periodic` → wait **0** always |
| Communicating modes | May wait only if delay>0 and deadline-energy / legacy rule allows |
| `fair_physical_decisions` | `message` / `periodic_broadcast` / `bid_exchange` = **info-only** (no claim/charge) |
| Physical claims | Only on `bid_assign`, `vehicle_idle`, `charge_end`, `service_end`, `pickup_missed`, `epoch` |

## Trace evidence (`peak_stress_seed101`)

| Treatment | Delay | OT | Mean assign wait | Deferred assigns | Phys claims | Info-only |
|-----------|------:|---:|-----------------:|-----------------:|------------:|----------:|
| none | 0 | 0.825 | **0** | 0 | 249 | 120 |
| none | 30 | **0.825** | **0** | 0 | 249 | 120 |
| none | 120 | **0.825** | **0** | 0 | 249 | 120 |
| periodic | 30 | 0.825 | **0** | 0 | 249 | 552 |
| selective | 30 | 0.775 | 37.5 | 40 | 237 | 324 |
| selective_deadline | 30 | 0.850 | 30 | 40 | 249 | 282 |

After correction, **none’s OT is invariant to the configured message delay** (no artificial wait). Periodic keeps the same physical claim count as none (249) while using more info-only ticks for broadcasts only.

## Ranking impact

Previous delayed rankings that treated “none waits like full” are **invalidated**. New 60-scenario closeout uses the corrected controls. Preserve PASS1 CSVs as historical only.
