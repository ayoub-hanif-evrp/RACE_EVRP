import numpy as np
import pandas as pd

from race_casablanca.demand.generator import generate_requests, zone_sampling_weights


def test_seeded_requests_are_reproducible():
    candidates = pd.DataFrame(
        {
            "commune": ["Anfa", "Anfa", "Hay Hassani", "Hay Hassani"],
            "category": ["shop=yes"] * 4,
            "lat": [33.59, 33.591, 33.58, 33.581],
            "lon": [-7.63, -7.631, -7.64, -7.641],
            "snap_node": [1, 2, 3, 4],
            "snap_distance_m": [10, 12, 8, 9],
            "accessible": [True, True, True, True],
        }
    )
    communes = pd.DataFrame(
        {
            "commune": ["Anfa", "Hay Hassani"],
            "zip_code": ["20040", "20220"],
            "population": [100000, 140000],
            "households": [20000, 26000],
            "density": [9000, 8000],
        }
    )
    land = pd.DataFrame(
        {
            "commune": ["Anfa", "Hay Hassani"],
            "zip_code": ["20040", "20220"],
            "Number of Commercial Buildings": [100, 80],
        }
    )
    config = {
        "generator_version": "0.1.0",
        "spatial": {"population_weight": 0.6, "commercial_weight": 0.4},
        "intensity_profiles": {
            "daytime_peak": {"weights": [0] * 8 + [1] * 8 + [0] * 8},
        },
    }
    regime = {
        "n_customers": 10,
        "start_hour": 8,
        "horizon_hours": 8,
        "service_duration_min": 8,
        "package_weight_kg": 5,
        "time_window_hours": 2,
        "intensity_profile": "daytime_peak",
        "urgency": "normal",
    }
    weights = zone_sampling_weights(communes, land, config)
    a = generate_requests(candidates, weights, "baseline_feasible", regime, config, seed=42)
    b = generate_requests(candidates, weights, "baseline_feasible", regime, config, seed=42)
    c = generate_requests(candidates, weights, "baseline_feasible", regime, config, seed=43)
    assert a["release_min"].tolist() == b["release_min"].tolist()
    assert a["lat"].tolist() == b["lat"].tolist()
    assert a["release_min"].tolist() != c["release_min"].tolist() or a["lat"].tolist() != c["lat"].tolist()
    assert not a["is_observed_order"].any()
