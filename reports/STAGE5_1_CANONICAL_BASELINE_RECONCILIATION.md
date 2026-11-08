# Stage 5.1 — Canonical baseline reconciliation

Do **not** mix Stage 4B / Stage 5 / Stage 5.1 metric tables as identical simulator versions.

## Known drifts

| Era | Peak SOC35 greedy→0.7 | Tight SOC35 greedy→0.7 | Notes |
| --- | ---: | ---: | --- |
| Stage 4B | 34/40 | 21/30 | Pre partial-charge planning fix; projection double-count possible |
| Stage 5 | 37/40 | 18/30 | After `target_kwh` planning fix |
| Stage 5.1 | **36/40** | **21/30** | Mode-specific projection + readiness equalized on RH arms |

Expected drivers of drift:

1. Partial-charge planning correction (Stage 5 A1).
2. SERVING/CHARGING projection correction (Stage 5.1 T1) — changes insertion feasibility mid-service/charge.
3. Readiness charging on SF-RH arms (Stage 5.1 T2).
4. Same seed/scenarios, but not bit-identical event traces across eras.

**Canonical evaluation implementation going forward:** Stage 5.1 simulator + policies (this commit). Re-cite only 5.1 CSVs for paper tables unless explicitly labeled historical.
