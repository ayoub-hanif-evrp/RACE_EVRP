"""Stage 4B: hard deadlines + discrete target-SOC depot charging."""

from __future__ import annotations

from race_casablanca.policies.charging_controller import ChargingController
from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import Request, RequestStatus, Stop, VehicleMode


class _ForceAssignThenShrinkPolicy:
    """Assign R1 with wide window, then shrink deadline so arrival is late."""

    name = "force_assign_shrink"

    def __init__(self) -> None:
        self._done = False

    def on_decision(self, obs: FullInfoObservation, actions: ActionInterface, reason: str) -> None:
        if self._done:
            return
        sim = actions._sim
        if "R1" not in sim.requests:
            return
        req = sim.requests["R1"]
        if req.status != RequestStatus.AVAILABLE:
            return
        ok = actions.claim_task("V1", "R1")
        if ok:
            # Adversarial: make deadline unreachable before arrival
            # Travel 0→3 = 180s; service 60s → need finish by tw_end
            req.tw_end_s = sim.now_s + 100.0  # arrival ~180 > 100 - service
            self._done = True


def test_late_arrival_cannot_complete_hard_deadline():
    base = make_two_request_scenario()
    # Drop R2; keep R1 with initially feasible window
    reqs = [
        Request(
            request_id="R1",
            snap_node=3,
            release_s=0.0,
            tw_start_s=0.0,
            tw_end_s=3600.0,
            service_s=60.0,
            weight_kg=10.0,
            status=RequestStatus.UNRELEASED,
        )
    ]
    sim = OnlineSimulator(
        scenario_id="stage4b/hard_deadline_adversarial",
        graph=base["graph"],
        model=base["model"],
        requests=reqs,
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(
            info_mode="full",
            seed=0,
            energy_uncertainty_delta=0.0,
            charge_on_return=False,
            auto_depot_when_idle_empty=False,
        ),
        policy=_ForceAssignThenShrinkPolicy(),
    )
    m = sim.run()
    assert sim.requests["R1"].status == RequestStatus.MISSED
    assert m.n_served == 0
    assert m.n_on_time == 0
    assert m.n_missed == 1
    assert m.on_time_rate_all == 0.0
    assert any(
        e.get("event") == "pickup_missed" and e.get("reason") == "deadline_unreachable_on_arrival"
        for e in sim.event_trace
    )


def test_impossible_injected_plan_misses_not_completes():
    """Bypass planner: depart to a pickup that was always impossible → MISSED."""
    base = make_two_request_scenario()
    reqs = [
        Request(
            request_id="R1",
            snap_node=3,
            release_s=0.0,
            tw_start_s=0.0,
            tw_end_s=100.0,  # travel 180 + service 60 >> 100
            service_s=60.0,
            weight_kg=10.0,
            status=RequestStatus.UNRELEASED,
        )
    ]
    sim = OnlineSimulator(
        scenario_id="stage4b/injected_impossible",
        graph=base["graph"],
        model=base["model"],
        requests=reqs,
        fleet=base["fleet"],
        depot_node=base["depot_node"],
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
    # Manually release and inject committed plan (planner would reject)
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    sim.now_s = 0.0
    sim.registry.try_claim("R1", "V1", 0.0)
    req = sim.requests["R1"]
    req.status = RequestStatus.COMMITTED
    req.owner = "V1"
    v = sim.vehicles["V1"]
    v.committed = ["R1"]
    v.plan = [Stop("pickup", "R1", 3)]
    sim._start_next_leg("V1")
    assert v.mode == VehicleMode.EN_ROUTE
    # Drain until arrival processed
    while sim._eq and sim.requests["R1"].status not in {
        RequestStatus.MISSED,
        RequestStatus.COMPLETED,
        RequestStatus.IN_SERVICE,
    }:
        from race_casablanca.sim.types import EventType

        ev = __import__("heapq").heappop(sim._eq)
        sim.now_s = ev.time_s
        if ev.type == EventType.VEHICLE_ARRIVAL:
            sim._on_arrival(ev.payload["vehicle_id"])
        elif ev.type == EventType.REQUEST_RELEASE:
            pass
    assert sim.requests["R1"].status == RequestStatus.MISSED
    assert sim.requests["R1"].on_time is False


def test_partial_charge_delivers_less_energy_than_full():
    base = make_two_request_scenario()
    # No requests — just charge at depot from mid SOC
    sim = OnlineSimulator(
        scenario_id="stage4b/partial_charge",
        graph=base["graph"],
        model=base["model"],
        requests=[],
        fleet={**base["fleet"], "initial_soc": 0.35},
        depot_node=base["depot_node"],
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
    v = sim.vehicles["V1"]
    assert abs(v.battery_kwh - 0.35 * bmax) < 1e-6
    # Charge to 0.70
    sim.request_return_depot("V1", charge=True, target_soc=0.70)
    while sim._eq:
        import heapq

        ev = heapq.heappop(sim._eq)
        sim.now_s = ev.time_s
        from race_casablanca.sim.types import EventType

        if ev.type == EventType.CHARGE_END:
            sim._on_charge_end(
                ev.payload["vehicle_id"],
                ev.payload["target_kwh"],
                energy_delivered=float(ev.payload.get("energy_to_deliver_kwh", 0.0)),
                duration_s=float(ev.payload.get("duration_s", 0.0)),
            )
        elif ev.type == EventType.VEHICLE_ARRIVAL:
            sim._on_arrival(ev.payload["vehicle_id"])
    expected_partial = 0.70 * bmax - 0.35 * bmax
    assert abs(v.energy_delivered_kwh - expected_partial) < 1e-6
    assert abs(v.battery_kwh - 0.70 * bmax) < 1e-6
    assert v.charge_duration_s > 0
    partial_delivered = v.energy_delivered_kwh
    partial_dur = v.charge_duration_s

    # Full charge from same start would deliver more
    sim2 = OnlineSimulator(
        scenario_id="stage4b/full_charge",
        graph=base["graph"],
        model=base["model"],
        requests=[],
        fleet={**base["fleet"], "initial_soc": 0.35},
        depot_node=base["depot_node"],
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
    sim2.request_return_depot("V1", charge=True, target_soc=1.0)
    while sim2._eq:
        import heapq

        ev = heapq.heappop(sim2._eq)
        sim2.now_s = ev.time_s
        from race_casablanca.sim.types import EventType

        if ev.type == EventType.CHARGE_END:
            sim2._on_charge_end(
                ev.payload["vehicle_id"],
                ev.payload["target_kwh"],
                energy_delivered=float(ev.payload.get("energy_to_deliver_kwh", 0.0)),
                duration_s=float(ev.payload.get("duration_s", 0.0)),
            )
        elif ev.type == EventType.VEHICLE_ARRIVAL:
            sim2._on_arrival(ev.payload["vehicle_id"])
    v2 = sim2.vehicles["V1"]
    assert v2.energy_delivered_kwh > partial_delivered + 1e-6
    assert v2.charge_duration_s > partial_dur + 1e-6
    assert abs(v2.battery_kwh - bmax) < 1e-6


def test_charging_controller_charge_to_07():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id="stage4b/ctrl07",
        graph=base["graph"],
        model=base["model"],
        requests=[],
        fleet={**base["fleet"], "initial_soc": 0.35},
        depot_node=base["depot_node"],
        shift_start_s=0.0,
        shift_end_s=3600.0,
        config=SimConfig(info_mode="full", seed=0, initial_soc=0.35, energy_uncertainty_delta=0.0),
        policy=None,
    )
    actions = ActionInterface(sim)
    ctrl = ChargingController(mode="charge_to_target", target_soc=0.70)
    n = ctrl.apply(sim, actions)
    assert n == 1
    assert any(s.kind == "depot_charge" and s.target_kwh is not None for s in sim.vehicles["V1"].plan)


def test_completed_implies_on_time_under_hard_deadlines():
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
    for r in sim.requests.values():
        if r.status == RequestStatus.COMPLETED:
            assert r.on_time is True
    assert m.n_on_time == m.n_served
    assert abs(m.on_time_rate - m.on_time_rate_all) < 1e-12
