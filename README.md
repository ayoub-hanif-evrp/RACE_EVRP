# LaDe-P Jilin pickup audit

Stage 1 of a new transportation-research project. The repository audits the published Jilin partition of [Cainiao-AI/LaDe-P](https://huggingface.co/datasets/Cainiao-AI/LaDe-P). It does not implement a simulator, a routing solver, or a learning model, and it does not depend on any earlier project code.

The suitability decision is **conditionally suitable**: the file can anchor observed pickup demand and courier-day event times. It does not observe electric vehicles, batteries, depots, or customer request-release times. Read `reports/DATASET_SUITABILITY.md` before any modeling.

## Install

Python 3.11 or newer is required. The audit was run with Python 3.12.10.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## Reproduce

```powershell
.\.venv\Scripts\python scripts\download_lade_p_jilin.py
.\.venv\Scripts\python scripts\analyze_jilin_pickup.py
.\.venv\Scripts\python -m pytest
```

The download copies the Jilin parquet and the dataset card at revision `f1ddd8dd163028dd5a8ab7d7c83b198ebd2f2167`. It exits with an error if the SHA-256 differs from the published Git-LFS object `043bdc91ff0c5906ac810e6097407226bc2c51da68bda6f40727f57aaf2737f9`. It does not create a substitute table.

Analysis prints the Arrow schema before any derived columns are built. Figures are written only from that verified file.

## Layout

| Path | Contents |
| --- | --- |
| `data/raw/` | Unmodified parquet and dataset-card snapshot |
| `data/processed/` | Audit tables and `audit_summary.json` |
| `data/manifests/` | Revision, URLs, checksums, license notes, citation |
| `scripts/` | Download and analysis entry points |
| `src/lade_audit/` | Parsing, integrity checks, summaries, figures |
| `figures/` | Five audit figures, PNG and PDF |
| `reports/` | Provenance, audit, research specification, suitability, handoff |
| `tests/` | Parsing and file-integrity tests |

## Citation

Wu et al., "LaDe: The First Comprehensive Last-mile Express Dataset from Industry," KDD 2024, pp. 5991–6002, https://doi.org/10.1145/3637528.3671548.

The Hugging Face card is tagged Apache-2.0. The paper states CC BY-NC 4.0. Both are recorded in `reports/DATA_PROVENANCE.md`.

## Boundary

Couriers in this table are not labeled as electric vehicles. Acceptance time is not customer request creation. Package weight, battery, energy, depot location, road travel time, and vehicle-to-vehicle communication are absent.
