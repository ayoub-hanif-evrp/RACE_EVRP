"""Solomon-style Casablanca instance classes (C/R/RC, sizes 15/30/45)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from race_casablanca.demand.generator import (
    _sample_zones_solomon_style,
    build_solomon_style_regime,
    generate_solomon_style_requests,
    load_demand_config,
)
from race_casablanca.paths import config_dir


def test_solomon_config_sizes_and_classes():
    cfg = load_demand_config(config_dir() / "demand_solomon_style.yaml")
    assert cfg["sizes"] == [15, 30, 45]
    for c in ("C1", "C2", "R1", "R2", "RC1", "RC2"):
        assert c in cfg["classes"]


def test_zone_patterns_differ():
    zones = [f"Z{i}" for i in range(10)]
    probs = np.linspace(0.02, 0.2, 10)
    probs = probs / probs.sum()
    rng_c = np.random.default_rng(0)
    rng_r = np.random.default_rng(0)
    c = _sample_zones_solomon_style(zones, probs, 60, "C", rng_c, n_cluster_zones=2)
    r = _sample_zones_solomon_style(zones, probs, 60, "R", rng_r, n_cluster_zones=2)
    assert len(set(c)) <= 2
    assert len(set(r)) >= 5


def test_build_regime_n_customers():
    cfg = load_demand_config(config_dir() / "demand_solomon_style.yaml")
    r15 = build_solomon_style_regime("C1", 15, cfg)
    r45 = build_solomon_style_regime("RC2", 45, cfg)
    assert r15["n_customers"] == 15
    assert r15["spatial_pattern"] == "C"
    assert r15["time_window_hours"] == 1.0
    assert r45["n_customers"] == 45
    assert r45["spatial_pattern"] == "RC"
    assert r45["time_window_hours"] == 3.0


def test_generate_solomon_request_counts():
    from race_casablanca.demand.generator import (
        load_demand_zone_weights,
        zone_sampling_weights_from_table,
    )
    from race_casablanca.paths import candidates_dir, zones_dir

    cfg = load_demand_config(config_dir() / "demand_solomon_style.yaml")
    weights = zone_sampling_weights_from_table(
        load_demand_zone_weights(zones_dir() / "demand_zone_weights.csv")
    )
    candidates = pd.read_csv(candidates_dir() / "pickup_candidates.csv")
    for n in (15, 30, 45):
        df = generate_solomon_style_requests(candidates, weights, "R1", n, cfg, seed=20_000_000 + n)
        assert len(df) == n
        assert set(df["n_customers"]) == {n}
        assert (df["is_observed_order"] == False).all()  # noqa: E712
