"""Stage 5.1: mode-specific projected_state_after_lock must not double-count travel."""

from __future__ import annotations

import heapq

from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.feasibility_check import projected_state_after_lock
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import EventType, Request, RequestStatus, Stop, VehicleMode


def _drain_until(sim, pred, max_events: int = 50):
    n = 0
    while sim._eq and n < max_events and not pred():
        ev = heapq.heappop(sim._eq)
        sim.now_s = ev.time_s
        if ev.type == EventType.VEHICLE_ARRIVAL:
            sim._on_arrival(ev.payload["vehicle_id"])
        elif ev.type == EventType.SERVICE_END:
            sim._on_service_end(ev.payload["vehicle_id"], ev.payload["request_id"])
        elif ev.type == EventType.CHARGE_END:
            sim._on_charge_end(
                ev.payload["vehicle_id"],
                ev.payload["target_kwh"],
                energy_delivered=float(ev.payload.get("energy_to_deliver_kwh", 0.0)),
                duration_s=float(ev.payload.get("duration_s", 0.0)),
            )
        n += 1


def test_projection_during_serving_does_not_rededuct_travel():
    base = make_two_request_scenario()
    reqs = [
        Request("R1", 3, 0.0, 0.0, 3600.0, 120.0, 10.0, status=RequestStatus.UNRELEASED),
    ]
    sim = OnlineSimulator(
        scenario_id="proj_serving",
        graph=base["graph"],
        model=base["model"],
        requests=reqs,
        fleet=base["fleet"],
        depot_node=0,
        shift_start_s=0.0,
        shift_end_s=8 * 3600.0,
        config=SimConfig(
            info_mode="full",
            seed=0,
            energy_uncertainty_delta=0.0,
            charge_on_return=False,
            auto_depot_when_idle_empty=False,
        ),
        policy=None,
    )
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    assert sim.try_assign("V1", "R1")
    _drain_until(sim, lambda: sim.vehicles["V1"].mode == VehicleMode.SERVING)
    v = sim.vehicles["V1"]
    assert v.mode == VehicleMode.SERVING
    bat_true = v.battery_kwh
    # Stale path_length must not be re-applied
    assert v.path_length_m > 0
    proj = projected_state_after_lock(
        v, sim.requests, sim.router, sim.energy, sim.depot_node, sim.now_s
    )
    assert abs(proj.battery_kwh - bat_true) < 1e-9
    assert proj.node == 3
    assert proj.ready_s >= sim.now_s + 1e-9 or proj.ready_s == sim.requests["R1"].service_start_s + 120.0
    # Double-count would subtract ~0.6 kWh again
    assert proj.battery_kwh > bat_true - 0.3  # equality; guard against large drop
    assert abs(proj.load_kg - 10.0) < 1e-9


def test_projection_during_charging_does_not_replay_depot_leg():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id="proj_charge",
        graph=base["graph"],
        model=base["model"],
        requests=[],
        fleet={**base["fleet"], "initial_soc": 0.35},
        depot_node=0,
        shift_start_s=0.0,
        shift_end_s=3600.0,
        config=SimConfig(
            info_mode="full",
            seed=0,
            initial_soc=0.35,
            energy_uncertainty_delta=0.0,
            charge_on_return=False,
            auto_depot_when_idle_empty=False,
        ),
        policy=None,
    )
    # Move away then return with partial charge so we have a path then CHARGING at depot
    v = sim.vehicles["V1"]
    # Direct charge at depot (already there)
    sim.request_return_depot("V1", charge=True, target_soc=0.70)
    _drain_until(sim, lambda: sim.vehicles["V1"].mode == VehicleMode.CHARGING)
    v = sim.vehicles["V1"]
    assert v.mode == VehicleMode.CHARGING
    bat_before_finish = v.battery_kwh
    proj = projected_state_after_lock(
        v, {}, sim.router, sim.energy, sim.depot_node, sim.now_s
    )
    assert proj.node == 0
    assert abs(proj.battery_kwh - 0.70 * sim.energy.battery_kwh_max) < 1e-6
    # Must not subtract another depot trip from battery
    assert proj.battery_kwh >= bat_before_finish - 1e-9
    assert proj.ready_s > sim.now_s


def test_projection_en_route_still_deducts_remaining():
    base = make_two_request_scenario()
    reqs = [Request("R1", 3, 0.0, 0.0, 3600.0, 60.0, 10.0, status=RequestStatus.UNRELEASED)]
    sim = OnlineSimulator(
        scenario_id="proj_enroute",
        graph=base["graph"],
        model=base["model"],
        requests=reqs,
        fleet=base["fleet"],
        depot_node=0,
        shift_start_s=0.0,
        shift_end_s=8 * 3600.0,
        config=SimConfig(
            info_mode="full",
            seed=0,
            energy_uncertainty_delta=0.0,
            charge_on_return=False,
            auto_depot_when_idle_empty=False,
        ),
        policy=None,
    )
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    assert sim.try_assign("V1", "R1")
    v = sim.vehicles["V1"]
    assert v.mode == VehicleMode.EN_ROUTE
    bat0 = v.battery_kwh
    proj = projected_state_after_lock(
        v, sim.requests, sim.router, sim.energy, sim.depot_node, sim.now_s
    )
    e_cons = sim.energy.conservative_kwh(v.path_length_m)
    assert abs(proj.battery_kwh - (bat0 - e_cons)) < 1e-9
    assert proj.node == 3
