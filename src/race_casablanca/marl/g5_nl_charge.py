"""Gate G5: partial NL charge vs always-full on energy-binding tiers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from race_casablanca.exact.charge_commit_enum import (
    enumerate_charge_commit,
    instance_c_partial_better,
)
from race_casablanca.marl.episode_sampler import ProceduralEpisodeGenerator
from race_casablanca.marl.seed_banks import episode_train_seed
from race_casablanca.policies import RaceCooperativePolicy
from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.types import RequestStatus


def _spread_vehicles_near_requests(sim: OnlineSimulator) -> None:
    snaps = [int(r.snap_node) for r in sim.requests.values() if r.snap_node is not None]
    if not snaps:
        return
    for i, vid in enumerate(sim.vehicles.keys()):
        v = sim.vehicles[vid]
        v.node = int(snaps[i % len(snaps)])
        v.ready_s = float(sim.now_s)


def nl_taper_costs(*, soc_from: float = 0.28) -> dict[str, float]:
    """Document CV taper: same start SOC, partial vs full wall-clock."""
    e = EnergyModel.from_fleet(
        {
            "usable_battery_kwh": 40.0,
            "consumption_wh_per_km": 200.0,
            "min_reserve_soc": 0.15,
            "charging_curve": {
                "soc_breakpoints": [0.0, 0.50, 0.80, 0.90, 0.95, 1.0],
                "cumulative_hours": [0.0, 0.91, 1.46, 1.72, 1.95, 2.40],
                "peak_power_kw": 22.0,
            },
        }
    )
    partial = e.charge_duration_s(soc_from=soc_from, soc_to=0.70)
    full = e.charge_duration_s(soc_from=soc_from, soc_to=1.00)
    taper = e.charge_duration_s(soc_from=0.70, soc_to=1.00)
    return {
        "soc_from": float(soc_from),
        "partial_to_0_70_s": float(partial),
        "full_to_1_00_s": float(full),
        "taper_0_70_to_1_00_s": float(taper),
        "full_over_partial": float(full / max(partial, 1e-9)),
    }


def exact_partial_beats_full() -> dict[str, Any]:
    r = enumerate_charge_commit(instance_c_partial_better())
    return {
        "instance": "C_partial_better",
        "best_on_time": int(r.best_on_time),
        "always_full_on_time": int(r.always_full_on_time),
        "gap": int(r.best_on_time - r.always_full_on_time),
        "pass": bool(r.best_on_time > r.always_full_on_time),
    }


def _run_native_charge(
    episode: dict,
    *,
    charge_target_soc: float,
    comm_mode: str = "full",
    seed: int = 0,
    spread_vehicles: bool = True,
) -> dict[str, float]:
    reqs = deepcopy(episode["requests"])
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    pol = RaceCooperativePolicy(
        comm_mode=comm_mode,
        enable_readiness_charge=True,
        charge_target_soc=float(charge_target_soc),
        rng_seed=7,
    )
    fleet = dict(episode["fleet"])
    nv = int(fleet.get("n_vehicles", 3))
    soc = float(fleet.get("initial_soc", 0.28))
    sim = OnlineSimulator(
        scenario_id=f"{episode['scenario_id']}/g5_tgt{charge_target_soc:.2f}",
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
            initial_soc=soc,
            n_vehicles=nv,
            message_delay_s=0.0,
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
    charge_s = float(sum(float(getattr(v, "charge_duration_s", 0.0) or 0.0) for v in sim.vehicles.values()))
    energy_kwh = float(
        sum(float(getattr(v, "energy_delivered_kwh", 0.0) or 0.0) for v in sim.vehicles.values())
    )
    n_charges = float(sum(1 for v in sim.vehicles.values() if float(getattr(v, "charge_duration_s", 0.0) or 0.0) > 0))
    return {
        "on_time_rate_all": float(m["on_time_rate_all"]),
        "n_served": float(m["n_served"]),
        "charge_duration_s": charge_s,
        "energy_delivered_kwh": energy_kwh,
        "n_charges": n_charges,
    }


def g5_binding_rows(
    *,
    n_episodes: int = 4,
    master_seed: int = 0,
    n_vehicles: int = 3,
    regime: str = "conflict_dense",
    partial_soc: float = 0.70,
    full_soc: float = 1.00,
    comm_mode: str = "full",
) -> list[dict[str, Any]]:
    """Compare partial vs always-full readiness charge on energy-binding episodes."""
    gen = ProceduralEpisodeGenerator.from_release(load_network=True)
    rows: list[dict[str, Any]] = []
    for ep in range(n_episodes):
        seed = episode_train_seed(master_seed, ep + 11000)
        episode = gen.make_episode(
            regime=regime,
            seed=seed,
            n_vehicles=n_vehicles,
            master_seed=master_seed,
            episode_index=ep,
            energy_binding=True,
        )
        part = _run_native_charge(episode, charge_target_soc=partial_soc, comm_mode=comm_mode, seed=seed)
        full = _run_native_charge(episode, charge_target_soc=full_soc, comm_mode=comm_mode, seed=seed)
        rows.append(
            {
                "episode_index": ep,
                "seed": seed,
                "partial_ot": part["on_time_rate_all"],
                "full_ot": full["on_time_rate_all"],
                "delta_ot": part["on_time_rate_all"] - full["on_time_rate_all"],
                "partial_charge_s": part["charge_duration_s"],
                "full_charge_s": full["charge_duration_s"],
                "partial_energy_kwh": part["energy_delivered_kwh"],
                "full_energy_kwh": full["energy_delivered_kwh"],
                "partial_n_charges": part["n_charges"],
                "full_n_charges": full["n_charges"],
            }
        )
    return rows


def summarize_g5(
    rows: list[dict[str, Any]],
    *,
    exact: dict[str, Any] | None = None,
    taper: dict[str, float] | None = None,
) -> dict[str, Any]:
    if not rows:
        return {"n_episodes": 0, "hard_pass": False, "soft_pass": False}
    mean_d = float(sum(float(r["delta_ot"]) for r in rows) / len(rows))
    mean_p = float(sum(float(r["partial_ot"]) for r in rows) / len(rows))
    mean_f = float(sum(float(r["full_ot"]) for r in rows) / len(rows))
    mean_pcs = float(sum(float(r["partial_charge_s"]) for r in rows) / len(rows))
    mean_fcs = float(sum(float(r["full_charge_s"]) for r in rows) / len(rows))
    n_pos = sum(1 for r in rows if float(r["delta_ot"]) > 1e-9)
    exact = exact or exact_partial_beats_full()
    taper = taper or nl_taper_costs()
    # Hard: online partial OT strictly beats full on mean, and exact structural win.
    hard = bool(mean_d > 0.0 and exact.get("pass"))
    # Soft: taper cost evidence + exact win, or online non-negative with less charge time.
    soft = bool(
        exact.get("pass")
        and (
            mean_d >= 0.0
            or (mean_fcs > mean_pcs * 1.1 and float(taper["full_over_partial"]) >= 1.5)
        )
    )
    return {
        "n_episodes": len(rows),
        "mean_partial_ot": mean_p,
        "mean_full_ot": mean_f,
        "mean_delta_ot": mean_d,
        "mean_partial_charge_s": mean_pcs,
        "mean_full_charge_s": mean_fcs,
        "n_episodes_partial_better": n_pos,
        "exact": exact,
        "nl_taper": taper,
        "hard_pass": hard,
        "soft_pass": soft or hard,
    }
