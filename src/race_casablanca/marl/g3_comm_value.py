"""Gate G3: communication must be load-bearing on conflict_dense (+ PO)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from race_casablanca.marl.episode_sampler import ProceduralEpisodeGenerator
from race_casablanca.policies import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.types import RequestStatus


def _spread_vehicles_near_requests(sim: OnlineSimulator) -> None:
    """Break depot-symmetry so peer bids can change owners (G3 load-bearing)."""
    snaps = [int(r.snap_node) for r in sim.requests.values() if r.snap_node is not None]
    if not snaps:
        return
    vids = list(sim.vehicles.keys())
    for i, vid in enumerate(vids):
        node = snaps[i % len(snaps)]
        v = sim.vehicles[vid]
        v.node = int(node)
        v.ready_s = float(sim.now_s)


def _run_native(
    episode: dict,
    *,
    comm_mode: str,
    soc: float,
    delay_s: float = 0.0,
    seed: int = 0,
    spread_vehicles: bool = True,
) -> dict[str, float]:
    reqs = deepcopy(episode["requests"])
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    pol = RaceCooperativePolicy(comm_mode=comm_mode, enable_readiness_charge=True, rng_seed=7)
    fleet = dict(episode["fleet"])
    nv = int(fleet.get("n_vehicles", 3))
    sim = OnlineSimulator(
        scenario_id=f"{episode['scenario_id']}/g3_{comm_mode}",
        graph=episode["graph"],
        model=episode["model"],
        requests=reqs,
        fleet=fleet,
        depot_node=episode["depot_node"],
        shift_start_s=episode["shift_start_s"],
        shift_end_s=episode["shift_end_s"],
        config=SimConfig(
            info_mode="restricted",
            seed=seed,
            initial_soc=float(fleet.get("initial_soc", soc)),
            n_vehicles=nv,
            message_delay_s=delay_s,
            packet_loss_p=0.0,
            periodic_state_broadcast=False,
            decision_on_release=True,
            day=str(episode.get("day", "Monday")),
        ),
        policy=pol,
    )
    if spread_vehicles:
        _spread_vehicles_near_requests(sim)
    m = sim.run().to_dict()
    return {
        "on_time_rate_all": float(m["on_time_rate_all"]),
        "n_served": float(m["n_served"]),
        "n_bid_messages": float(getattr(sim, "n_bid_messages", 0) or 0),
        "n_bid_bytes": float(getattr(sim, "n_bid_bytes", 0) or 0),
    }


def conflict_comm_ablation_rows(
    *,
    n_episodes: int = 6,
    master_seed: int = 0,
    n_vehicles: int = 3,
    soc: float = 0.35,
    delay_s: float = 0.0,
    energy_binding: bool = False,
) -> list[dict[str, Any]]:
    """Compare native full vs none on procedural conflict_dense episodes."""
    gen = ProceduralEpisodeGenerator.from_release(load_network=True)
    rows: list[dict[str, Any]] = []
    from race_casablanca.marl.seed_banks import episode_train_seed

    for ep in range(n_episodes):
        seed = episode_train_seed(master_seed, ep + 9000)
        episode = gen.make_episode(
            regime="conflict_dense",
            seed=seed,
            n_vehicles=n_vehicles,
            master_seed=master_seed,
            episode_index=ep,
            energy_binding=energy_binding,
        )
        none_m = _run_native(episode, comm_mode="none", soc=soc, delay_s=delay_s)
        full_m = _run_native(episode, comm_mode="full", soc=soc, delay_s=delay_s)
        rows.append(
            {
                "episode_index": ep,
                "scenario_id": episode["scenario_id"],
                "seed": seed,
                "none_ot": none_m["on_time_rate_all"],
                "full_ot": full_m["on_time_rate_all"],
                "delta_ot": full_m["on_time_rate_all"] - none_m["on_time_rate_all"],
                "none_msgs": none_m["n_bid_messages"],
                "full_msgs": full_m["n_bid_messages"],
            }
        )
    return rows


def mean_comm_delta_ot(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return float(sum(float(r["delta_ot"]) for r in rows) / len(rows))
