# FINAL METHOD REPRODUCIBILITY

## Environment

- OS: Windows 10/11 (build from user_info 10.0.26200)
- Python: project `.venv` (`.\.venv\Scripts\python.exe`)
- `PYTHONPATH=src`
- Dependencies: see `pyproject.toml` / installed venv (includes osmnx, networkx, pandas, numpy, pytest)

## Seeds / fixed knobs

- Simulator `SimConfig.seed=0`
- Policy `rng_seed=7`
- Pilot SOC `0.35`, `n_vehicles=3`
- `RANDOM_P_SEND=0.25` (bandwidth reference only; not used by selective arms)
- Scenarios listed in `data/casablanca/online_results/race_csc_pilot_config.json`
- **locked_final: not used**

## Commands

```powershell
$env:PYTHONPATH = "src"
$py = (Resolve-Path .\.venv\Scripts\python.exe).Path

# Correctness
& $py -m pytest tests/test_race_csc.py tests/test_timing_causality.py `
  tests/test_deadline_commit_wait.py tests/test_communication_value_cases.py `
  tests/test_trust_horizon.py tests/test_race_cooperative.py `
  tests/test_race_comm_protocol_v2.py -q --tb=line

# Causal pilot (~20–30 min on 4 workers)
& $py scripts/run_race_csc_pilot.py --workers 4 `
  | Tee-Object -FilePath data/casablanca/online_results/race_csc_pilot_run.log

# Paired summary helper
& $py scripts/_analyze_csc_pilot.py
```

## Outputs

| File | Role |
|------|------|
| `data/casablanca/online_results/race_csc_pilot.csv` | Raw episode rows |
| `.../race_csc_pilot_summary.csv` | Treatment × delay means |
| `.../race_csc_pilot_paired.json` | Paired scenario contrasts |
| `.../race_csc_pilot_config.json` | Exact arms / scenarios |
| `.../race_csc_pilot_event_trace_sample.json` | Sample ownership/comm counters @30 s |
| `.../race_csc_pilot_run.log` | Console log |

## Code entry points

- `src/race_casablanca/coordination/race_csc.py`
- `src/race_casablanca/policies/race_cooperative.py` (`claim_mode`, wait authority, version hygiene)
- `src/race_casablanca/coordination/task_bids.py` (`claim_intent`, `owned`)

## Resource use (this run)

- ~246 jobs × ~14–23 s mean wall ⇒ ~1295 s wall with 4 workers.
