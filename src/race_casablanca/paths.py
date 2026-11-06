"""Project paths for the Casablanca benchmark."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def casablanca_root() -> Path:
    return project_root() / "data" / "casablanca"


def raw_dir() -> Path:
    return casablanca_root() / "raw"


def roads_dir() -> Path:
    return casablanca_root() / "roads"


def traffic_dir() -> Path:
    return casablanca_root() / "traffic"


def zones_dir() -> Path:
    return casablanca_root() / "zones"


def candidates_dir() -> Path:
    return casablanca_root() / "pickup_candidates"


def scenarios_dir() -> Path:
    return casablanca_root() / "scenarios"


def fleet_dir() -> Path:
    return casablanca_root() / "fleet"


def manifest_dir() -> Path:
    return casablanca_root() / "manifests"


def figure_dir() -> Path:
    return project_root() / "figures"


def report_dir() -> Path:
    return project_root() / "reports"


def config_dir() -> Path:
    return project_root() / "configs"
