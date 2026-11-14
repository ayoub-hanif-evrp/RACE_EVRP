# RACE-CERT — Causal Validation

## Same routing controller across treatments

All A–G use `RaceCooperativePolicy` claim/charge logic (hybrid only swaps `_maybe_communicate`). Hybrid parity check: native full ≡ hybrid full (OT and owners) on `peak_stress_seed101`.

## Counterfactuals executed

| Contrast | Finding |
|----------|---------|
| Full vs none (delay 0) | OT +1.1 pp; ownership differs (see deltas CSV) |
| Full vs selective | OT tied; bytes ×0.35 |
| Full vs certified | OT tied; bytes ×0.39; cert suppress fires |
| Selective vs certified | OT tied; certified slightly more bytes |
| Full vs learned | OT tied; learned ≈ full bytes (no causal bandwidth effect) |
| Delay 30: none vs selective/certified | OT tied at 0.801 on this development set |

## What counts as a causal communication success

A change in **message volume** is not success unless it alters ownership and/or service, or matches full service at materially lower bandwidth.

- Selective and certified: **match full service** at much lower bandwidth → causal efficiency success vs full.
- Learned: **no** bandwidth causality (full volume).
- Certified vs selective: **no** additional causal win.

## Deterministic delivery path

Zero-delay bids ingest before `bid_assign` (two-phase). Delayed setting uses `message_delay_s=30` without full flooding (full+delay skipped as known pathology).
