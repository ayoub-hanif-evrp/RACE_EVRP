"""Phase 1 slice 1: sequential_native claim resolve vs batched_legacy."""

from __future__ import annotations

from copy import deepcopy

import pytest

from race_casablanca.marl.env import (
    ABLATION_D,
    OP_DEFER,
    RaceMultiAgentEnv,
)
from race_casablanca.sim.synthetic import make_line_graph, make_unit_congestion
from race_casablanca.sim.types import Request, RequestStatus


def _three_vehicle_one_request_factory():
    """Two idle peers + one request: classic simultaneous-claim conflict setup."""

    graph = make_line_graph()
    model = make_unit_congestion()
    req = Request(
        request_id="R1",
        snap_node=3,
        release_s=0.0,
        tw_start_s=0.0,
        tw_end_s=7200.0,
        service_s=60.0,
        weight_kg=10.0,
        status=RequestStatus.UNRELEASED,
    )
    fleet = {
        "usable_battery_kwh": 40.0,
        "payload_kg": 600.0,
        "initial_soc": 1.0,
        "min_reserve_soc": 0.15,
        "consumption_wh_per_km": 200.0,
        "peak_charge_power_kw": 22.0,
        "n_vehicles": 3,
    }

    def factory(seed=0, n_vehicles=3):
        r = deepcopy(req)
        r.status = RequestStatus.UNRELEASED
        r.owner = None
        return {
            "scenario_id": "synthetic/three_v_one_r",
            "graph": graph,
            "model": model,
            "requests": [r],
            "fleet": {**fleet, "n_vehicles": n_vehicles},
            "depot_node": 0,
            "shift_start_s": 0.0,
            "shift_end_s": 8 * 3600.0,
            "day": "Monday",
        }

    return factory


def test_default_claim_resolve_mode_is_sequential_native():
    env = RaceMultiAgentEnv(
        scenario_factory=_three_vehicle_one_request_factory(),
        n_vehicles=3,
        ablation=ABLATION_D,
        seed=0,
        max_decisions=50,
    )
    assert env.claim_resolve_mode == "sequential_native"


def test_invalid_claim_resolve_mode_rejected():
    with pytest.raises(ValueError, match="claim_resolve_mode"):
        RaceMultiAgentEnv(
            scenario_factory=_three_vehicle_one_request_factory(),
            n_vehicles=3,
            claim_resolve_mode="not_a_mode",
        )


def _force_all_claim_task0(env: RaceMultiAgentEnv) -> dict[str, tuple[int, int]]:
    """Every agent proposes claim index 0 + suppress comm (duplicate-op stress)."""
    from race_casablanca.marl.env import COMM_SUPPRESS

    out = {}
    for vid, obs in env._pending_obs.items():
        tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)
        out[vid] = (0 if tasks else OP_DEFER, COMM_SUPPRESS)
    return out


def test_sequential_native_single_owner_under_duplicate_claims():
    """All agents propose the same task; exactly one owner after sequential resolve."""
    factory = _three_vehicle_one_request_factory()
    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ABLATION_D,
        seed=0,
        max_decisions=20,
        initial_soc=1.0,
        claim_resolve_mode="sequential_native",
    )
    env.reset(seed=0)
    # Advance until the request is announced (release decision epoch).
    for _ in range(30):
        steps = env.step(_force_all_claim_task0(env))
        owners = [r.owner for r in env.sim.requests.values() if r.owner]
        if owners:
            assert len(owners) == 1
            assert env.final_metrics()["claim_resolve_mode"] == "sequential_native"
            return
        if list(steps.values())[0].done:
            break
    pytest.fail("request was never claimed under sequential_native")


def test_batched_legacy_still_available():
    factory = _three_vehicle_one_request_factory()
    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ABLATION_D,
        seed=0,
        max_decisions=20,
        initial_soc=1.0,
        claim_resolve_mode="batched_legacy",
    )
    env.reset(seed=0)
    for _ in range(30):
        steps = env.step(_force_all_claim_task0(env))
        owners = [r.owner for r in env.sim.requests.values() if r.owner]
        if owners:
            assert len(owners) == 1
            assert env.final_metrics()["claim_resolve_mode"] == "batched_legacy"
            return
        if list(steps.values())[0].done:
            break
    pytest.fail("request was never claimed under batched_legacy")


def test_intent_matched_teacher_ot_via_env_step():
    """intent_matched + env.step must stay competitive (native applied, step advances)."""
    from race_casablanca.marl.bc import NativeBridgeTeacher
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    paths = resolve_eval_dirs()
    if not paths:
        pytest.skip("no eval scenarios")
    graph = load_drive_graph()
    model = load_congestion_model()
    sc = load_scenario(paths[0], load_network=False, graph=graph, model=model)
    reqs0 = deepcopy(sc.requests)

    def factory(seed=0, n_vehicles=3):
        reqs = deepcopy(reqs0)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        return {
            "scenario_id": sc.scenario_id,
            "graph": graph,
            "model": model,
            "requests": reqs,
            "fleet": {**sc.fleet, "n_vehicles": 3},
            "depot_node": sc.depot_node,
            "shift_start_s": sc.shift_start_s,
            "shift_end_s": sc.shift_end_s,
            "day": getattr(sc, "day", "Monday"),
        }

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ABLATION_D,
        seed=0,
        max_decisions=2000,
        initial_soc=0.35,
        claim_resolve_mode="sequential_native",
    )
    teacher = NativeBridgeTeacher(mode="intent_matched")
    env.reset(seed=0)
    while True:
        steps = env.step(teacher.actions(env))
        if list(steps.values())[0].done:
            break
    ot = float(env.final_metrics().get("on_time_rate_all", 0.0))
    assert ot >= 0.70, f"intent_matched step OT too low: {ot}"


@pytest.mark.slow
def test_g1_execute_teacher_within_3pp_of_native_mean():
    """Gate G1: native-execute teacher in MARL env within 3 pp mean OT of native."""
    from race_casablanca.marl.parity import mean_delta_ot, parity_rows
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    paths = resolve_eval_dirs()
    if len(paths) < 6:
        pytest.skip(f"need ≥6 eval scenarios, found {len(paths)}")
    graph = load_drive_graph()
    model = load_congestion_model()
    scenarios = [
        load_scenario(p, load_network=False, graph=graph, model=model) for p in paths[:6]
    ]
    rows = parity_rows(scenarios, graph, model, teacher_mode="execute")
    mean_d = mean_delta_ot(rows)
    assert mean_d >= -0.03, (
        f"G1 fail: mean delta OT={mean_d:.4f} (need ≥ -0.03). rows={rows}"
    )


@pytest.mark.slow
def test_g1_intent_matched_step_within_3pp_of_native_mean():
    """Gate G1 (step path): intent_matched through env.step within 3 pp of native."""
    from race_casablanca.marl.parity import mean_delta_ot, parity_rows
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    paths = resolve_eval_dirs()
    if len(paths) < 6:
        pytest.skip(f"need ≥6 eval scenarios, found {len(paths)}")
    graph = load_drive_graph()
    model = load_congestion_model()
    scenarios = [
        load_scenario(p, load_network=False, graph=graph, model=model) for p in paths[:6]
    ]
    rows = parity_rows(scenarios, graph, model, teacher_mode="intent_matched")
    mean_d = mean_delta_ot(rows)
    assert mean_d >= -0.03, (
        f"G1 intent_matched fail: mean delta OT={mean_d:.4f}. rows={rows}"
    )
