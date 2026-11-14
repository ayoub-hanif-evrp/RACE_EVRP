# RACE-CERT — Fast-Track Pilot Results

Artifacts: `data/casablanca/online_results/race_fasttrack_pilot*.csv/json`, `race_fasttrack_hybrid_parity.json`.

Development scenarios via `resolve_eval_dirs()`; SOC=0.35; 3 EVs. **Not** locked final.

## Milestone 1 — Hybrid parity

| Check | Result |
|-------|--------|
| Native full vs hybrid full (`peak_stress_seed101`) | OT **0.875 = 0.875**, owner Hamming **0** |

Routing/charging controller is preserved under the hybrid wrapper.

## Delay = 0 — mean OT / bytes / messages

| Treatment | Mean OT | Mean bytes | Mean msgs | Notes |
|-----------|---------|------------|-----------|-------|
| A none | 0.821 | 0 | 0 | |
| B full | **0.832** | 253946 | 643 | reference |
| C periodic | 0.821 | 0 | 0 | task-bid path not exercised by periodic flag |
| D random matched | 0.818 | 104139 | 261 | budget=129 msgs target from selective |
| E selective | **0.832** | **59089** | 129 | **best byte efficiency among OT-matched** |
| F certified | **0.832** | 65814 | 129 | same OT; ~58.5 cert resolutions/ep; 0 ambiguous fallbacks |
| G learned (BC of selective) | **0.832** | 253946 | 643 | collapses to full volume |

Byte ratio vs full: selective **0.348**, certified **0.387**, learned **1.0**.

## Delay = 30 s (none / selective / certified)

| Treatment | Mean OT | Mean bytes |
|-----------|---------|------------|
| none | 0.801 | 0 |
| selective | 0.801 | 57908 |
| certified | 0.801 | 64374 |

No OT separation under delay on this set; both selective and certified track none’s OT here (allocation effects muted at 30 s on these scenarios).

## Causal notes

- Selective and certified match full OT at delay 0 with ~65–61% fewer bytes.
- Certified does **not** beat selective on bandwidth (slightly larger payloads from interval fields; same message count).
- Learned gate fails to reduce traffic (sends like full).
- Random matched underperforms slightly on OT vs full.

## Certification counters (delay 0)

Mean `n_certified_resolutions` ≈ 58.5 / episode; `n_ambiguous_fallbacks` ≈ 0 — local views often dominate or singleton-feasible after representation, but initial/material send rules still emit ~129 messages (same as selective).
