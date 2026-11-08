# Stage 5 — Novelty and limitations

## What is already known

- Exact EVRPTW with partial recharging and labeling (Desaulniers et al., OR 2016, DOI 10.1287/opre.2016.1535).
- Time-dependent EVRPTW with ALNS + exact charging subproblems (Erdelić et al., CIE 2026, DOI 10.1016/j.cie.2025.111758).
- State-space-time joint route/charge optimization with replanning (Liu et al., TRE 2025, DOI 10.1016/j.tre.2025.104233).
- Rolling-horizon routing combined with charging-schedule search is established in recent dynamic EV literature.

## What RACE-RH is

An online service-first rolling horizon with an inner discrete-target charging DP on Casablanca, under locked commitments and conservative energy. Implementation + physics repair are real engineering contributions to this repository.

## What it does **not** establish

- No service advantage over equalized greedy charge-to-0.7 / SF-RH-0.7 on train peak/tight SOC35.
- No proven label-dominance theorem beyond optional weak keys.
- No computational speed win (frequent timeouts; DP cost high).
- Novelty relative to published joint routing/charging methods remains **unresolved**; current evidence is closer to an application of known decomposition ideas than a new exact method.

## Limitations

- Inner DP insertion pattern is bounded (leading/between/trailing), not full charge-anywhere.
- `commit_fleet_plans` charge-augmented path is new; SF-RH charge-aware post-hoc path was weak in Stage 5 runs.
- Train-only diagnostics; no held-out test campaign (reserved for Stage 6 if pursued).
