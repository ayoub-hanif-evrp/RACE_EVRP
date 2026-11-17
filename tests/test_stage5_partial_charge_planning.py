"""Stage 5 A1: planning must respect Stop.target_kwh (match simulator)."""

from __future__ import annotations

from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.feasibility_check import (
    apply_depot_charge,
    projected_state_after_lock,
    simulate_plan_conservative,
)
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import ProjectedState, Request, RequestStatus, Stop, VehicleMode


def _energy(bmax: float = 40.0, peak_kw: float = 22.0) -> EnergyModel:
    return EnergyModel(
        consumption_kwh_per_km=0.2,
        uncertainty_delta=0.0,
        battery_kwh_max=bmax,
        reserve_soc=0.15,
        peak_charge_power_kw=peak_kw,
    )


def test_apply_depot_charge_targets():
    e = _energy()
    for soc, expect in [(0.50, 20.0), (0.70, 28.0), (1.00, 40.0)]:
        stop = Stop("depot_charge", None, 0, target_kwh=soc * e.battery_kwh_max)
        bat, ready, need = apply_depot_charge(14.0, 100.0, e, stop)
        assert abs(bat - expect) < 1e-9
        assert abs(need - (expect - 14.0)) < 1e-9
        dur = e.charge_duration_kwh(kwh_from=14.0, kwh_to=expect)
        assert abs(ready - (100.0 + dur)) < 1e-9


def test_simulate_plan_respects_partial_target():
    from race_casablanca.sim.router import RouteCache

    base = make_two_request_scenario()
    e = _energy()
    router = RouteCache(base["graph"], base["model"], day="Monday")
    origin = ProjectedState(node=0, ready_s=0.0, battery_kwh=14.0, load_kg=0.0)
    plan = [Stop("depot_charge", None, 0, target_kwh=0.70 * 40.0)]
    chk = simulate_plan_conservative(
        origin, plan, {}, router, e, 0, 600.0, 1e9, require_depot_return=False
    )
    assert chk.feasible
    assert abs(chk.final_battery_kwh - 28.0) < 1e-6


def test_full_charge_enables_far_trip_partial_does_not():
    """Pickup requiring near-full battery: 50% charge leaves energy infeasible; 100% ok."""
    from race_casablanca.sim.router import RouteCache

    base = make_two_request_scenario()
    router = RouteCache(base["graph"], base["model"], day="Monday")
    e = EnergyModel(
        consumption_kwh_per_km=4.0,
        uncertainty_delta=0.0,
        battery_kwh_max=40.0,
        reserve_soc=0.15,
        peak_charge_power_kw=22.0,
    )
    req = Request("R1", 3, 0.0, 0.0, 50000.0, 60.0, 10.0, status=RequestStatus.AVAILABLE)
    origin = ProjectedState(node=0, ready_s=0.0, battery_kwh=14.0, load_kg=0.0)
    plan50 = [
        Stop("depot_charge", None, 0, target_kwh=20.0),
        Stop("pickup", "R1", 3),
    ]
    plan100 = [
        Stop("depot_charge", None, 0, target_kwh=40.0),
        Stop("pickup", "R1", 3),
    ]
    chk50 = simulate_plan_conservative(origin, plan50, {"R1": req}, router, e, 0, 600.0, 1e9)
    chk100 = simulate_plan_conservative(origin, plan100, {"R1": req}, router, e, 0, 600.0, 1e9)
    assert not chk50.feasible
    assert chk100.feasible


def test_partial_charge_beats_full_on_tight_deadline():
    """Partial charge finishes in time; full charge duration misses tw_end (non-linear)."""
    from race_casablanca.sim.router import RouteCache

    base = make_two_request_scenario()
    router = RouteCache(base["graph"], base["model"], day="Monday")
    e = EnergyModel(
        consumption_kwh_per_km=0.2,
        uncertainty_delta=0.0,
        battery_kwh_max=40.0,
        reserve_soc=0.15,
        peak_charge_power_kw=22.0,
    )
    # 14→20 ≈ 983s; 14→40 ≈ 6347s under NL curve at 22 kW peak
    req = Request("R1", 3, 0.0, 0.0, 4000.0, 60.0, 10.0, status=RequestStatus.AVAILABLE)
    origin = ProjectedState(node=0, ready_s=0.0, battery_kwh=14.0, load_kg=0.0)
    plan50 = [Stop("depot_charge", None, 0, target_kwh=20.0), Stop("pickup", "R1", 3)]
    plan100 = [Stop("depot_charge", None, 0, target_kwh=40.0), Stop("pickup", "R1", 3)]
    chk50 = simulate_plan_conservative(origin, plan50, {"R1": req}, router, e, 0, 600.0, 1e9)
    chk100 = simulate_plan_conservative(origin, plan100, {"R1": req}, router, e, 0, 600.0, 1e9)
    assert chk50.feasible
    assert not chk100.feasible
    assert chk100.reason == "time_window"


def test_projected_lock_uses_partial_target():
    from race_casablanca.sim.router import RouteCache

    base = make_two_request_scenario()
    router = RouteCache(base["graph"], base["model"], day="Monday")
    e = _energy()
    sim = OnlineSimulator(
        scenario_id="t",
        graph=base["graph"],
        model=base["model"],
        requests=[],
        fleet=base["fleet"],
        depot_node=0,
        shift_start_s=0.0,
        shift_end_s=3600.0,
        config=SimConfig(info_mode="full", seed=0, initial_soc=0.35, energy_uncertainty_delta=0.0),
        policy=None,
        router=router,
    )
    v = sim.vehicles["V1"]
    v.battery_kwh = 14.0
    v.node = 0
    v.busy = True
    v.mode = VehicleMode.EN_ROUTE
    v.moving_to = Stop("depot_charge", None, 0, target_kwh=28.0)
    v.path_length_m = 0.0
    v.en_route_conservative_kwh = 0.0
    v.departed_s = 0.0
    proj = projected_state_after_lock(v, {}, router, e, 0, 0.0)
    assert abs(proj.battery_kwh - 28.0) < 1e-6
    assert proj.battery_kwh < 39.0


def test_plan_sim_matches_physical_charge_metrics():
    """Deterministic energy: planned delivered energy equals simulated."""
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id="phys",
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
    bmax = sim.energy.battery_kwh_max
    before = sim.vehicles["V1"].battery_kwh
    target_soc = 0.70
    planned_need = max(0.0, target_soc * bmax - before)
    planned_dur = sim.energy.charge_duration_kwh(kwh_from=before, kwh_to=target_soc * bmax)
    sim.request_return_depot("V1", charge=True, target_soc=target_soc)
    import heapq
    from race_casablanca.sim.types import EventType

    while sim._eq:
        ev = heapq.heappop(sim._eq)
        sim.now_s = ev.time_s
        if ev.type == EventType.CHARGE_END:
            sim._on_charge_end(
                ev.payload["vehicle_id"],
                float(ev.payload["target_kwh"]),
                energy_delivered=float(ev.payload.get("energy_to_deliver_kwh", 0.0)),
                duration_s=float(ev.payload.get("duration_s", 0.0)),
            )
            break
        if ev.type == EventType.VEHICLE_ARRIVAL:
            sim._on_arrival(ev.payload["vehicle_id"])
    after = sim.vehicles["V1"].battery_kwh
    assert abs((after - before) - planned_need) < 1e-6
    assert abs(sim.vehicles["V1"].charge_duration_s - planned_dur) < 1e-6
