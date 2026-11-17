"""C/R/RC Casablanca instances on realistic OSM building/POI frame."""

from __future__ import annotations

import numpy as np
import pandas as pd

from race_casablanca.demand.generator import (
    _sample_zones_solomon_style,
    build_solomon_style_regime,
    generate_solomon_style_requests,
    load_demand_config,
)
from race_casablanca.demand.realistic_frame import filter_realistic_pickup_candidates
from race_casablanca.paths import candidates_dir, config_dir, zones_dir


def test_classes_are_crc_only():
    cfg = load_demand_config(config_dir() / "demand_solomon_style.yaml")
    assert list(cfg["classes"].keys()) == ["C", "R", "RC"]
    assert cfg["sizes"] == [15, 30, 45]
    assert "C1" not in cfg["classes"]


def test_realistic_frame_excludes_building_yes_and_parking():
    raw = pd.read_csv(candidates_dir() / "pickup_candidates.csv")
    filt = filter_realistic_pickup_candidates(raw)
    assert len(filt) > 1000
    assert not (filt["category"] == "building=yes").any()
    assert not filt["category"].isin(["amenity=parking", "amenity=fuel"]).any()
    assert filt["is_random_map_projection"].eq(False).all()


def test_zone_patterns_c_vs_r():
    zones = [f"Z{i}" for i in range(10)]
    probs = np.linspace(0.02, 0.2, 10)
    probs = probs / probs.sum()
    c = _sample_zones_solomon_style(zones, probs, 60, "C", np.random.default_rng(0), n_cluster_zones=2)
    r = _sample_zones_solomon_style(zones, probs, 60, "R", np.random.default_rng(0), n_cluster_zones=2)
    assert len(set(c)) <= 2
    assert len(set(r)) >= 5


def test_generate_on_realistic_buildings():
    from race_casablanca.demand.generator import (
        load_demand_zone_weights,
        zone_sampling_weights_from_table,
    )

    cfg = load_demand_config(config_dir() / "demand_solomon_style.yaml")
    weights = zone_sampling_weights_from_table(
        load_demand_zone_weights(zones_dir() / "demand_zone_weights.csv")
    )
    candidates = filter_realistic_pickup_candidates(
        pd.read_csv(candidates_dir() / "pickup_candidates.csv")
    )
    for cls, n in (("C", 15), ("R", 30), ("RC", 45)):
        df = generate_solomon_style_requests(candidates, weights, cls, n, cfg, seed=20_000_100 + n)
        assert len(df) == n
        assert df["snap_node"].notna().all()
        assert (df["is_observed_order"] == False).all()  # noqa: E712
        assert set(df["instance_class"]) == {cls}


def test_build_regime_crc():
    cfg = load_demand_config(config_dir() / "demand_solomon_style.yaml")
    r = build_solomon_style_regime("RC", 30, cfg)
    assert r["spatial_pattern"] == "RC"
    assert r["n_customers"] == 30
