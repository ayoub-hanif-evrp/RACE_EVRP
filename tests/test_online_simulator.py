"""Online simulator: synthetic exact routing/energy and basic Casablanca smoke."""

from __future__ import annotations

from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.synthetic import make_line_graph, make_two_request_scenario, make_unit_congestion


def test_synthetic_route_and_energy_exact():
    g = make_line_graph()
    model = make_unit_congestion()
    router = RouteCache(g, model, day="Monday")
    rt = router.route(0, 3, 0.0)
    assert rt.length_m == 3000.0
    assert abs(rt.duration_s - 180.0) < 1e-6
    energy = EnergyModel(0.2, 0.0, 40.0, 0.15, 22.0)
    assert abs(energy.nominal_kwh(3000.0) - 0.6) < 1e-12
    assert abs(energy.conservative_kwh(3000.0) - 0.6) < 1e-12


def test_synthetic_greedy_episode_serves_and_conserves_energy():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, energy_uncertainty_delta=0.0),
        policy=GreedyInsertionPolicy(),
    )
    m = sim.run()
    assert m.n_served >= 1
    assert m.payload_violations == 0
    # Energy conservation: consumed ≈ distance * 0.2 kWh/km
    expected = (m.total_distance_m / 1000.0) * 0.2
    assert abs(m.energy_consumed_kwh - expected) < 1e-9
    v = sim.vehicles["V1"]
    assert abs((40.0 - v.battery_kwh) - m.energy_consumed_kwh) < 1e-9


def test_reproducibility_same_seed():
    def once(seed: int):
        base = make_two_request_scenario()
        sim = OnlineSimulator(
            scenario_id=base["scenario_id"],
            graph=base["graph"],
            model=base["model"],
            requests=base["requests"],
            fleet=base["fleet"],
            depot_node=base["depot_node"],
            shift_start_s=base["shift_start_s"],
            shift_end_s=base["shift_end_s"],
            config=SimConfig(info_mode="full", seed=seed, energy_uncertainty_delta=0.2),
            policy=GreedyInsertionPolicy(),
        )
        return sim.run().to_dict()

    a = once(7)
    b = once(7)
    assert a["energy_consumed_kwh"] == b["energy_consumed_kwh"]
    assert a["total_distance_m"] == b["total_distance_m"]
    assert a["n_served"] == b["n_served"]
