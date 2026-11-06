"""Project paths. All outputs stay inside this repository."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def raw_dir() -> Path:
    return project_root() / "data" / "raw"


def processed_dir() -> Path:
    return project_root() / "data" / "processed"


def manifest_dir() -> Path:
    return project_root() / "data" / "manifests"


def figure_dir() -> Path:
    return project_root() / "figures"


def report_dir() -> Path:
    return project_root() / "reports"


def raw_parquet_path() -> Path:
    from lade_audit.constants import RAW_PARQUET_NAME

    return raw_dir() / RAW_PARQUET_NAME


def manifest_path() -> Path:
    return manifest_dir() / "lade_p_jilin_manifest.json"
