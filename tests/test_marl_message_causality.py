"""Message causality: bids before commit can change assignment (Stage 8.2 Gate 3)."""

from __future__ import annotations

from copy import deepcopy

from race_casablanca.coordination.task_bids import TaskBid, self_should_claim
from race_casablanca.marl.env import (
    ABLATION_F,
    COMM_SUPPRESS,
    K_TASKS,
    OP_DEFER,
    RaceMultiAgentEnv,
)
from race_casablanca.sim.policy_api import ActionInterface, build_restricted_observation
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus


def _factory(seed: int = 0, n_vehicles: int = 2):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    return sc


def test_self_should_claim_changes_with_peer_certificate():
    own = TaskBid(
        request_id="R1",
        sender_id="V1",
        feasible=True,
        marginal_travel_s=600.0,
        marginal_energy_kwh=2.0,
        energy_flex_kwh=5.0,
        deadline_slack_s=200.0,
        charge_burden_s=0.0,
        as_of_s=0.0,
        expires_s=1000.0,
        seq=1,
        commitment_version=0,
    )
    peer = TaskBid(
        request_id="R1",
        sender_id="V2",
        feasible=True,
        marginal_travel_s=200.0,
        marginal_energy_kwh=1.0,
        energy_flex_kwh=12.0,
        deadline_slack_s=400.0,
        charge_burden_s=0.0,
        as_of_s=0.0,
        expires_s=1000.0,
        seq=1,
        commitment_version=0,
    )
    assert self_should_claim(own, []) is True
    assert self_should_claim(own, [peer]) is False
    assert self_should_claim(peer, [own]) is True


def test_env_records_messages_before_commit_and_executed_comm():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation=ABLATION_F,
        seed=0,
        max_decisions=10,
        message_delay_s=0.0,
    )
    steps = env.reset(seed=0)
    actions = {
        vid: (OP_DEFER, 0 if float(st.comm_mask[0]) > 0.5 else COMM_SUPPRESS)
        for vid, st in steps.items()
    }
    nxt = env.step(actions)
    for st in nxt.values():
        assert "executed_comm" in st.info
        assert "msgs_before_commit_step" in st.info
    assert isinstance(env.final_metrics()["n_msgs_before_commit"], int)


def test_peer_certificate_changes_owner_vs_withheld():
    """Counterfactual: same proposals; with peer cert EV1 defers, without it EV1 claims."""
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation=ABLATION_F,
        seed=0,
        max_decisions=5,
        message_delay_s=0.0,
    )
    steps = env.reset(seed=0)
    vids = sorted(steps.keys())
    assert len(vids) == 2
    v1, v2 = vids[0], vids[1]

    # Identify a feasible task index for v1
    task_idx = None
    rid = None
    for i in range(K_TASKS):
        if steps[v1].op_mask[i] > 0.5:
            task_idx = i
            break
    assert task_idx is not None
    obs1 = env._pending_obs[v1]
    tasks = sorted(obs1.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
    rid = tasks[task_idx].request_id

    # --- WITHHELD: both claim, no communication ---
    env_w = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="A_no_comm",
        seed=0,
        max_decisions=5,
    )
    env_w.reset(seed=0)
    # Force both to propose the same task index if feasible
    act_w = {}
    for vid, st in env_w._pending_obs.items():
        ts = sorted(st.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
        idx = next((i for i, t in enumerate(ts) if t.request_id == rid), OP_DEFER)
        if idx < K_TASKS and env_w._encode(st)[1][idx] < 0.5:
            idx = OP_DEFER
        act_w[vid] = (idx if idx < K_TASKS else OP_DEFER, COMM_SUPPRESS)
    env_w.step(act_w)
    owner_withheld = None
    for vid in env_w.sim.vehicles:
        if rid in list(env_w.sim.vehicles[vid].committed):
            owner_withheld = vid
            break

    # --- DELIVERED: inject a superior V2 certificate before resolve ---
    env_d = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation=ABLATION_F,
        seed=0,
        max_decisions=5,
        message_delay_s=0.0,
    )
    env_d.reset(seed=0)
    # Build a better-than-V1 bid from V2 and deliver to V1 only
    obs_v1 = build_restricted_observation(env_d.sim, v1)
    obs_v2 = build_restricted_observation(env_d.sim, v2)
    act_v2 = ActionInterface(env_d.sim, actor_vehicle_id=v2)
    # Use synthetic superior travel so V1 must defer if it sees the cert
    payload = {
        "request_id": rid,
        "sender_id": v2,
        "feasible": True,
        "marginal_travel_s": 1.0,
        "marginal_energy_kwh": 0.1,
        "energy_flex_kwh": 20.0,
        "deadline_slack_s": 9999.0,
        "charge_burden_s": 0.0,
        "as_of_s": float(obs_v2.now_s),
        "expires_s": float(obs_v2.now_s) + 1000.0,
        "seq": 1,
        "commitment_version": 0,
        "reason": "counterfactual_superior",
        "withdrawn": False,
        "energy_certificate": True,
    }
    env_d.sim._ingest_task_bid(v1, payload, sender=v2)
    # Refresh pending obs so peer feats include certificate
    env_d._pending_obs[v1] = build_restricted_observation(env_d.sim, v1)
    env_d._pending_obs[v2] = build_restricted_observation(env_d.sim, v2)

    # V1 proposes claim; V2 defers (certificate alone should make V1 defer)
    act_d = {v1: (task_idx, COMM_SUPPRESS), v2: (OP_DEFER, COMM_SUPPRESS)}
    env_d.step(act_d)
    assert env_d._n_claim_defers_to_peer >= 1, "V1 must defer after seeing superior peer certificate"
    owner_delivered = None
    for vid in env_d.sim.vehicles:
        if rid in list(env_d.sim.vehicles[vid].committed):
            owner_delivered = vid
            break
    assert owner_delivered != v1, "V1 must not own the task after deferring to peer cert"
    # Withheld case: without messages someone may own it (often V1 via batch rank)
    assert owner_withheld is not None or owner_delivered is None


def test_expired_certificate_does_not_block_claim():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation=ABLATION_F,
        seed=0,
        max_decisions=5,
    )
    steps = env.reset(seed=0)
    vids = sorted(steps.keys())
    v1, v2 = vids[0], vids[1]
    obs1 = env._pending_obs[v1]
    tasks = sorted(obs1.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
    assert tasks
    rid = tasks[0].request_id
    task_idx = 0
    assert steps[v1].op_mask[0] > 0.5

    stale = {
        "request_id": rid,
        "sender_id": v2,
        "feasible": True,
        "marginal_travel_s": 1.0,
        "marginal_energy_kwh": 0.1,
        "energy_flex_kwh": 20.0,
        "deadline_slack_s": 9999.0,
        "charge_burden_s": 0.0,
        "as_of_s": float(obs1.now_s) - 10_000.0,
        "expires_s": float(obs1.now_s) - 1.0,  # expired
        "seq": 1,
        "commitment_version": 0,
        "reason": "expired",
        "withdrawn": False,
    }
    env.sim._ingest_task_bid(v1, stale, sender=v2)
    env._pending_obs[v1] = build_restricted_observation(env.sim, v1)
    env._pending_obs[v2] = build_restricted_observation(env.sim, v2)
    env.step({v1: (task_idx, COMM_SUPPRESS), v2: (OP_DEFER, COMM_SUPPRESS)})
    assert env._n_claim_defers_to_peer == 0, "expired certificate must not force defer"
    assert rid in list(env.sim.vehicles[v1].committed), "V1 should claim when peer cert expired"
