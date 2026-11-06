"""Fleet bounds, witness energy bookkeeping, and split isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from race_casablanca.paths import config_dir, fleet_dir, scenarios_dir


def test_fleet_and_package_bounds():
    fleet = yaml.safe_load((config_dir() / "fleet_default.yaml").read_text(encoding="utf-8"))
    assert fleet["usable_battery_kwh"] > 0
    assert fleet["payload_kg"] > 0
    assert 0 < fleet["min_reserve_soc"] < 1
    assert fleet["depot_charging"] == "depot_only"
    demand = yaml.safe_load((config_dir() / "demand_default.yaml").read_text(encoding="utf-8"))
    for regime in demand["regimes"].values():
        assert regime["package_weight_kg"] <= fleet["payload_kg"]
        assert regime["n_customers"] > 0


def test_witness_energy_feasibility_when_present():
    witnesses = list(scenarios_dir().rglob("reference_schedule.csv"))
    if not witnesses:
        pytest.skip("no witnesses generated")
    fleet = yaml.safe_load((config_dir() / "fleet_default.yaml").read_text(encoding="utf-8"))
    reserve = float(fleet["usable_battery_kwh"]) * float(fleet["min_reserve_soc"])
    for path in witnesses:
        df = pd.read_csv(path)
        assert df["witness_only"].all()
        assert df["battery_after_kwh"].min() >= reserve - 1e-6


def test_split_seed_isolation():
    demand = yaml.safe_load((config_dir() / "demand_default.yaml").read_text(encoding="utf-8"))
    train = set(demand["splits"]["train_seeds"])
    val = set(demand["splits"]["validation_seeds"])
    test = set(demand["splits"]["test_seeds"])
    assert train.isdisjoint(val)
    assert train.isdisjoint(test)
    assert val.isdisjoint(test)


def test_depot_is_labeled_scenario_only():
    path = fleet_dir() / "depot.json"
    if not path.exists():
        pytest.skip("depot not written")
    depot = json.loads(path.read_text(encoding="utf-8"))
    assert "not" in depot.get("note", "").lower() or "scenario" in depot.get("label", "").lower()
