# RACE-CERT Fast-Track — Handoff

**Status:** COMPLETE — pilot decision **PARTIAL**  
**Base commit:** `e5dc953` (+ this follow-up commit)

## Deliverables

| Report | Path |
|--------|------|
| Method | `reports/RACE_FASTTRACK_METHOD.md` |
| Certification | `reports/RACE_FASTTRACK_CERTIFICATION.md` |
| Causal validation | `reports/RACE_FASTTRACK_CAUSAL_VALIDATION.md` |
| Pilot results | `reports/RACE_FASTTRACK_PILOT_RESULTS.md` |
| Decision | `reports/RACE_FASTTRACK_DECISION.md` |
| Handoff | this file |

## Code

- `coordination/certifying_protocol.py`
- `coordination/learned_comm_gate.py`
- `policies/race_cert_hybrid.py`
- `scripts/run_race_fasttrack_pilot.py`
- `tests/test_race_cert_protocol.py`

## Key numbers (dev set, delay 0)

| Method | OT | Bytes vs full |
|--------|-----|---------------|
| full | 0.832 | 1.00 |
| selective | 0.832 | 0.35 |
| certified | 0.832 | 0.39 |
| learned | 0.832 | 1.00 |
| none | 0.821 | 0 |

## Next

Frozen evaluation + manuscript centered on **non-learning selective / certifying communication** with fixed native routing — not MAPPO routing recovery.
