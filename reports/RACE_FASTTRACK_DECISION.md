# RACE-CERT — Scientific Go / No-Go

## Decision: **PARTIAL**

### What is credible

1. **Hybrid control works.** Native cooperative routing+charging is frozen; communication is pluggable; full-comm hybrid reproduces native full owners/OT.
2. **Non-learning selective communication** remains the strongest empirical protocol: matches full OT (0.832) at ~35% of full bytes on the development set.
3. **Decision-certifying heuristic** is implemented with explicit assumptions (A1–A4), counters, and tests. It matches full OT and reduces bytes vs full (~39% of full), with measurable certified suppressions.
4. Stopping joint MAPPO routing retrain was the right call (Stage 8.3 evidence).

### What is *not* shown

1. Certified does **not** improve on selective (same OT, slightly worse bytes).
2. Lightweight **learned** send/suppress does **not** help (reverts to full traffic).
3. Heuristic intervals are **not** a proved travel-time theorem — labeled `heuristic_interval_v1`.
4. Development-set OT gaps remain small (~1.1 pp full vs none); byte reduction is the stronger signal and still needs locked-final confirmation.

### Principal contribution to take forward

**Keep the non-learning energy-certified selective (and optionally the formalized certifying gate as a principled sibling) under the fixed native cooperative controller.**

Do **not** start another large neural routing architecture. Do **not** claim MARL communication superiority.

### Next action (allowed)

If writing a methods paper: freeze selective (+ document certification formalism as optional/principled variant), run **one** pre-registered locked-final evaluation with delays/fleet sizes, and draft the manuscript around safe distributed bidding with decision-relevant messaging — compared to full / random-matched / centralized greedy.

If seeking a stronger CERT empirical edge: only a **bounded** refinement of the send rule to beat selective on bytes *without* OT loss — not a new architecture. Otherwise accept selective as the lead method.

### Stop

Fast-track pilot ends here. No Stage 8.4-style MAPPO routing campaign.
