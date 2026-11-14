# Delay Failure Diagnosis (PASS-1 Follow-up)

**Artifact:** `data/casablanca/online_results/race_delay_diagnosis.csv` (6 development scenarios × treatments × delays 0/30/120).

## Question

Why does peer communication reduce on-time service relative to **no communication** under 30–120 s delay?

## Measured mechanism (matched exogenous scenarios)

| Delay | Mode | Mean OT | Mean assign wait (s) | Deferred assigns / ep | Peer defers | Stale peers ignored | Mean bytes |
|------:|------|--------:|---------------------:|----------------------:|------------:|--------------------:|-----------:|
| 30 | none | **0.801** | 37.5 | 32 | 0 | 0 | 0 |
| 30 | full | 0.761 | 37.5 | 32 | 61.5 | 0 | 333825 |
| 30 | selective | 0.775 | 37.5 | 32 | **82.2** | 0 | 103395 |
| 30 | ecom | 0.775 | 37.5 | 32 | 63.8 | 0 | 84533 |
| 30 | selective_deadline | **0.801** | 30.0 | 32 | **0** | 5.7 | 60527 |
| 30 | ecom_deadline | **0.801** | 30.0 | 32 | **0** | 5.7 | 52379 |
| 120 | none | **0.799** | 120 | 32 | 0 | 0 | 0 |
| 120 | selective | 0.786 | 120 | 32 | 54.8 | 0 | 127264 |
| 120 | ecom | 0.783 | 120 | 32 | 21.5 | 0 | 71717 |
| 120 | selective_deadline | 0.792 | 60 | 32 | 0 | 0 | 50768 |
| 120 | periodic | **0.832** | 120 | 32 | 0 | 0 | 178708 |

## Separation of costs

1. **Physical assignment wait** is nearly **identical** for none vs full/selective at a fixed delay (legacy rule waits `min(max_wait, 1.25×delay, slack−urgency)`). Wait alone does **not** explain why none beats full.
2. **Communication byte volume** is not the causal OT driver: high-byte full and mid-byte selective both lose OT vs none; deadline variants cut bytes **and** recover OT.
3. **Causal driver:** `n_defers_to_peer` under delay. Delayed bids remain TTL-fresh and cause vehicles to **yield ownership to peers who looked better at stale as-of times**, producing worse realized service. None never defers → higher OT.
4. Missed/expired counts stay small; damage appears as fewer on-time completions after bad ownership, with higher vehicle idle wait under chatty delayed modes.

## Implication for method refinement

A justified EV-specific rule is **not** “send fewer certificate bytes.” It is:

- Prefer **commit-now** when delay consumes TW slack (`deadline_energy_assignment_wait_s`).
- Do **not defer** to peer bids older than a delay-scaled trust horizon (`delay_aware_trust`).

On this 6-scenario sample, that recovers OT to the none baseline at 30 s and near-none at 120 s, while keeping bytes well below selective/full.

## Caveats

- Six scenarios only; expanded 60-scenario ensemble required for stability.
- Periodic at 120 s shows high OT with zero assign-time deferrals — useful baseline, not a certificate method.
- Zero-delay behavior of deadline variants matches selective (no new advantage when delay=0).
