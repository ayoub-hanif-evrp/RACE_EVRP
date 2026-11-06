# Stage 1 handoff

Stage 1 is complete. No simulator, road network, routing solver, or learning algorithm was built.

## Decision

**CONDITIONALLY SUITABLE.**

LaDe-P Jilin can carry the demand and event-time side of an online pickup study. Electric energy, depot-only charging, request release, and vehicle-to-vehicle communication are not in the file and cannot be reported as measurements. The full argument is in `reports/DATASET_SUITABILITY.md`. The candidate problem written under that limit is `reports/RESEARCH_PROBLEM_V1.md`.

## What was executed

Environment: Python 3.12.10. Installed from `pyproject.toml`: pandas 3.1.1, pyarrow 26.0.1, NumPy 2.5.4, Matplotlib 3.11.2, Hugging Face Hub 2.4.0, pytest 9.2.0.

Download, 2026-11-06:

```text
Revision:   f1ddd8dd163028dd5a8ab7d7c83b198ebd2f2167
File:       data/pickup_jl-00000-of-00001-9b430a56a935f284.parquet
SHA-256:    043bdc91ff0c5906ac810e6097407226bc2c51da68bda6f40727f57aaf2737f9
Bytes:      20772658
Verified against published LFS oid: True
```

Analysis after the Arrow schema check:

```text
Rows in parquet metadata: 261801
Tasks: 261801
Couriers: 665
Business dates: 184
Courier-days: 18880
```

Tests:

```text
6 passed in 0.44s
```

The tests check clock and business-date parsing, the open-task count, the pinned checksum and schema, city value `Jilin`, and uniqueness of `order_id`.

## Artifacts

| Path | Role |
| --- | --- |
| `data/raw/pickup_jl-00000-of-00001-9b430a56a935f284.parquet` | Unmodified Jilin partition |
| `data/raw/LaDe-P_README.md` | Dataset card at the same revision |
| `data/manifests/lade_p_jilin_manifest.json` | Revision, URLs, checksums, license statements, citation |
| `data/processed/audit_summary.json` | Full numerical audit |
| `data/processed/daily_task_counts.parquet` | Tasks and couriers by business date |
| `data/processed/courier_day_summary.parquet` | One row per courier-day |
| `figures/fig1_daily_pickup_volumes.pdf` | Daily volume |
| `figures/fig2_tasks_per_courier_day.pdf` | Tasks per courier-day |
| `figures/fig3_geographic_distribution.pdf` | Stop map |
| `figures/fig4_time_windows.pdf` | Window length and start hour |
| `figures/fig5_acceptance_and_completion.pdf` | Acceptance hour, completion hour, delay |
| `reports/DATA_PROVENANCE.md` | Source and license record |
| `reports/DATASET_AUDIT.md` | Schema, counts, and the observed / derived / missing table |
| `reports/RESEARCH_PROBLEM_V1.md` | Candidate problem under the audit |
| `reports/DATASET_SUITABILITY.md` | Suitability decision |

PNG copies of the figures sit beside the PDFs. Re-run with:

```powershell
.\.venv\Scripts\python scripts\download_lade_p_jilin.py
.\.venv\Scripts\python scripts\analyze_jilin_pickup.py
.\.venv\Scripts\python -m pytest
```

## Facts the next stage has to live with

- Couriers are not identified as electric vehicles.
- `accept_time` is acceptance, not customer request creation. It precedes the window on 85.1% of tasks.
- `ds` is a month-day code, matches every completion date, and contains no year. The span is 1 May–31 October, with a volume ramp in early May and a trough on 21–25 June.
- Duties are real: median 8 tasks, 90.1% of acceptances occur with other accepted work still open, and later acceptances are common.
- Geography has two regimes. Eleven regions hold 79.3% of stops within 20 km of the median. Four regions hold 54,181 stops more than 50 km away, with only six couriers in both.
- Accept GPS is missing on 31.3% of rows and pickup GPS on 16.1%. A few dozen GPS points are more than 50 km from the stop.
- No depot, weight, battery, energy, road time, or communication field exists in the table.
- The Hugging Face card says Apache-2.0. The paper says CC BY-NC 4.0. That conflict is unresolved.

## Decisions required before any implementation

1. **Claim boundary.** Confirm that the paper will treat energy, charging, release time, and communication as counterfactuals. If the required claim is stronger, stop and find different data.
2. **Assignment.** Hold each historical courier-day fixed and only resequence it, or also reassign tasks across couriers. The audit supports the first. The second cannot be checked against a dispatcher log.
3. **Release convention.** Use `accept_time` as the vehicle's information time, with that limitation written into the problem, or do not use this file as a release process.
4. **Who counts as a vehicle.** Decide a minimum number of active days. One hundred one single-day couriers hold almost no tasks. One hundred sixty-six couriers with at least 30 days hold 93.8%.
5. **Geography.** Use the eleven-region component, the four far regions, or both as separate scenarios.
6. **Depot rule.** Choose an explicit synthetic depot. Personal start GPS is a candidate input for a minority of couriers and is not a measured depot.
7. **Travel and energy.** Choose external models and label every energy number as simulated. Do not fit them to acceptance-to-completion time.
8. **Windows.** Decide how completions before the window opens are scored. They are 29.0% of the historical outcomes.
9. **Sensitivity holds.** Decide whether early May and 21–25 June stay in the main sample.
10. **License.** Resolve Apache-2.0 versus CC BY-NC 4.0 before the data or a derived release leaves the project. Cite Wu et al., KDD 2024, either way.

## Stop line

Stage 1 ends here. The next stage, if these decisions are made, would be the first mathematical specification of the counterfactual problem. It is not authorized by this handoff alone.
