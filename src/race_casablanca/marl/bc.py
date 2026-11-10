"""Behavior cloning from a local greedy / cooperative teacher (training aid only)."""

from __future__ import annotations

from typing import Callable

import numpy as np
import torch
import torch.nn.functional as F

from race_casablanca.marl.env import (
    COMM_SUPPRESS,
    K_TASKS,
    OP_CHARGE,
    OP_DEFER,
    RaceMultiAgentEnv,
)
from race_casablanca.marl.nets import FactorizedActor
from race_casablanca.sim.policy_api import ActionInterface


def greedy_teacher_actions(env: RaceMultiAgentEnv) -> dict[str, tuple[int, int]]:
    """Local teacher: claim feasible task with least travel; charge if SoC low; else defer.

    Communication: send bid for the chosen claim target if selective/full; else suppress.
    Uses only restricted ActionInterface (no peer truth).
    """
    assert env.sim is not None
    out = {}
    for vid, obs in env._pending_obs.items():
        act = ActionInterface(env.sim, actor_vehicle_id=vid)
        tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
        best_i = None
        best_travel = float("inf")
        for i, t in enumerate(tasks):
            chk = act.check_insertion(vid, t.request_id)
            if chk.feasible:
                travel = float(chk.marginal_travel_s or 0.0)
                if travel < best_travel:
                    best_travel = travel
                    best_i = i
        soc = float(obs.self_state.battery_kwh) / 40.0
        if best_i is not None:
            op = best_i
        elif soc < 0.25:
            op = OP_CHARGE
        else:
            op = OP_DEFER
        if env.comm_enabled and best_i is not None and env.ablation != "A_no_comm":
            if env.ablation in ("B_full_comm", "D_selective", "E_selective_no_energy", "F_race_marl"):
                # Selective: send only if energy flex is tight or competition likely
                chk = act.check_insertion(vid, tasks[best_i].request_id)
                flex = float(chk.energy_flex_kwh or 0.0)
                comm = best_i if (env.ablation == "B_full_comm" or flex < 8.0) else COMM_SUPPRESS
            else:
                comm = COMM_SUPPRESS
        else:
            comm = COMM_SUPPRESS
        out[vid] = (op, comm)
    return out


def collect_bc_batch(
    env: RaceMultiAgentEnv,
    *,
    n_steps: int = 128,
    seed: int = 0,
) -> dict[str, np.ndarray]:
    steps = env.reset(seed=seed)
    obs_l, op_l, comm_l, opm_l, cmm_l = [], [], [], [], []
    ep_seed = seed
    for _ in range(n_steps):
        teacher = greedy_teacher_actions(env)
        for vid, st in steps.items():
            obs_l.append(st.obs)
            op_l.append(teacher[vid][0])
            comm_l.append(teacher[vid][1])
            opm_l.append(st.op_mask)
            cmm_l.append(st.comm_mask)
        steps = env.step(teacher)
        if list(steps.values())[0].done:
            ep_seed += 1
            steps = env.reset(seed=ep_seed)
    return {
        "obs": np.asarray(obs_l, dtype=np.float32),
        "op": np.asarray(op_l, dtype=np.int64),
        "comm": np.asarray(comm_l, dtype=np.int64),
        "op_mask": np.asarray(opm_l, dtype=np.float32),
        "comm_mask": np.asarray(cmm_l, dtype=np.float32),
    }


def behavior_clone(
    actor: FactorizedActor,
    batch: dict[str, np.ndarray],
    *,
    epochs: int = 20,
    lr: float = 1e-3,
    device: str | torch.device = "cpu",
) -> list[float]:
    device = torch.device(device)
    actor = actor.to(device)
    opt = torch.optim.Adam(actor.parameters(), lr=lr)
    obs = torch.as_tensor(batch["obs"], device=device)
    op = torch.as_tensor(batch["op"], device=device)
    comm = torch.as_tensor(batch["comm"], device=device)
    opm = torch.as_tensor(batch["op_mask"], device=device)
    cmm = torch.as_tensor(batch["comm_mask"], device=device)
    losses = []
    for _ in range(epochs):
        op_logits, comm_logits = actor(obs, opm, cmm)
        loss = F.cross_entropy(op_logits, op) + F.cross_entropy(comm_logits, comm)
        opt.zero_grad()
        loss.backward()
        opt.step()
        losses.append(float(loss.item()))
    return losses
