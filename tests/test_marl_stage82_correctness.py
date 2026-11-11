"""Stage 8.2 scientific-correctness tests (Gates 1)."""

from __future__ import annotations

import numpy as np
import torch

from race_casablanca.marl.buffer import compute_gae_time
from race_casablanca.marl.env import (
    ABLATION_A,
    ABLATION_B,
    ABLATION_C,
    ABLATION_D,
    ABLATION_E,
    ABLATION_F,
    COMM_SUPPRESS,
    RaceMultiAgentEnv,
)
from race_casablanca.marl.mappo import MAPPOTrainer
from race_casablanca.sim.synthetic import make_two_request_scenario


def _factory(seed: int = 0, n_vehicles: int = 3):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    sc["scenario_id"] = f"{sc.get('scenario_id', 'syn')}/s{seed}"
    return sc


def _env(ablation: str, **kw) -> RaceMultiAgentEnv:
    n_vehicles = kw.pop("n_vehicles", 3)
    max_decisions = kw.pop("max_decisions", 30)
    return RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=n_vehicles,
        ablation=ablation,
        seed=0,
        max_decisions=max_decisions,
        message_delay_s=0.0,
        **kw,
    )


def test_e_keeps_own_battery_strips_peer_energy_only():
    env = _env(ABLATION_E)
    steps = env.reset(seed=1)
    for st in steps.values():
        # feats[0] is own battery — must be non-zero at initial SoC 0.35
        assert float(st.obs[0]) > 0.1, "E must retain own battery observation"
    # Force a send and inspect payload energy fields via sim local_bids after step
    actions = {vid: (COMM_SUPPRESS, 0) for vid in steps}  # claim suppress idx wrong — use defer+send0
    from race_casablanca.marl.env import OP_DEFER

    actions = {vid: (OP_DEFER, 0) for vid in steps}
    env.step(actions)
    # Any delivered bid under E must have zeroed energy certificate fields
    for recipient, by_rid in env.sim.local_bids.items():
        for rid, senders in by_rid.items():
            for sid, payload in senders.items():
                assert float(payload.get("energy_flex_kwh", 0.0)) == 0.0
                assert payload.get("energy_certificate", True) is False


def test_f_comm_mask_stricter_than_d_on_uncritical_tasks():
    """F enables send only for contested/energy-critical tasks; D is freer."""
    d = _env(ABLATION_D)
    f = _env(ABLATION_F)
    sd = d.reset(seed=2)
    sf = f.reset(seed=2)
    # Same scenario seed ⇒ same announced set; F mask ⊆ D mask for send slots
    for vid in sd:
        d_send = sd[vid].comm_mask[:5]
        f_send = sf[vid].comm_mask[:5]
        assert np.all(f_send <= d_send + 1e-6), "F send mask must be subset of D"


def test_gae_cuts_across_episode_reset_boundary():
    """Two episodes in one buffer: large reward in ep2 must not inflate ep1 adv."""
    # Episode 1: r=0, V=0, done/trunc boundary
    # Episode 2: r=100, V=0, done
    rewards = np.array([0.0, 100.0], dtype=np.float32)
    values = np.array([0.0, 0.0], dtype=np.float32)
    dones = np.array([1.0, 1.0], dtype=np.float32)
    truncs = np.array([0.0, 0.0], dtype=np.float32)
    adv, _ = compute_gae_time(rewards, values, dones, truncs, last_value=0.0, gamma=0.99, lam=0.95)
    assert abs(adv[0]) < 1e-5, f"ep1 advantage leaked: {adv[0]}"
    assert abs(adv[1] - 100.0) < 1e-5

    # Same with trunc boundary (admin cut + reset)
    dones2 = np.array([0.0, 1.0], dtype=np.float32)
    truncs2 = np.array([1.0, 0.0], dtype=np.float32)
    adv2, _ = compute_gae_time(rewards, values, dones2, truncs2, last_value=0.0, gamma=0.99, lam=0.95)
    assert abs(adv2[0]) < 1e-5, f"trunc boundary leaked: {adv2[0]}"


def test_external_comm_produces_no_comm_head_gradient():
    """B full-comm: executed comm is forced; PPO must not train comm head on samples."""
    torch.manual_seed(0)
    env = _env(ABLATION_B, max_decisions=20)
    trainer = MAPPOTrainer(env, lr=1e-3, epochs=1, device="cpu")
    # Zero-init-ish: run one collect/update and check comm-specific grads ~0 when learnable_frac=0
    buf, boot, _ = trainer.collect(8)
    assert all(x < 0.5 for row in buf.comm_learnable for x in np.asarray(row).ravel())
    # Manual update step inspecting grads
    adv_t, ret_t, adv_flat, ret_flat = buf.compute_gae(boot, gamma=0.99, lam=0.95, time_aware=False)
    adv_flat = (adv_flat - adv_flat.mean()) / (adv_flat.std() + 1e-8)
    data = buf.as_tensors(adv_flat, ret_flat, trainer.device)
    op_logits, comm_logits = trainer.actor(data["obs"], data["op_masks"], data["comm_masks"])
    from torch.distributions import Categorical
    import torch.nn.functional as F

    op_dist = Categorical(logits=op_logits)
    comm_dist = Categorical(logits=comm_logits)
    learn = data["comm_learnable"]
    new_op = op_dist.log_prob(data["op_actions"])
    new_comm = comm_dist.log_prob(data["comm_actions"])
    old = data["op_logprobs"] + learn * data["comm_logprobs"]
    new = new_op + learn * new_comm
    ratio = torch.exp(new - old)
    loss = -(torch.min(ratio * data["advantages"], ratio * data["advantages"])).mean()
    loss = loss + 0.5 * F.mse_loss(
        trainer.critic(torch.as_tensor(np.asarray(buf.global_obs), dtype=torch.float32)),
        torch.as_tensor(ret_t, dtype=torch.float32),
    )
    trainer.opt.zero_grad()
    loss.backward()
    comm_grad = 0.0
    for name, p in trainer.actor.named_parameters():
        if "comm" in name.lower() and p.grad is not None:
            comm_grad += float(p.grad.norm().item())
    assert learn.mean().item() < 1e-6
    assert comm_grad < 1e-6, f"spurious comm grad under B: {comm_grad}"


def test_bid_before_commit_messages_counted():
    env = _env(ABLATION_F)
    steps = env.reset(seed=3)
    from race_casablanca.marl.env import OP_DEFER

    # Everyone defers but tries to send task 0 if mask allows
    actions = {}
    for vid, st in steps.items():
        send = 0 if float(st.comm_mask[0]) > 0.5 else COMM_SUPPRESS
        actions[vid] = (OP_DEFER, send)
    nxt = env.step(actions)
    info = list(nxt.values())[0].info
    assert "msgs_before_commit_step" in info
    assert env._n_msgs_before_commit == info["msgs_before_commit_step"]
    m = env.final_metrics()
    assert isinstance(m["n_msgs_before_commit"], int)
    # If any agent had a legal send mask, at least one pre-commit message is expected on F
    if any(float(steps[vid].comm_mask[0]) > 0.5 for vid in steps):
        assert m["n_msgs_before_commit"] >= 1


def test_batched_claim_order_invariant_tiebreak():
    """Permuting dict insertion order must not change owners (sorted resolution)."""
    env = _env(ABLATION_A, max_decisions=5)
    steps = env.reset(seed=7)
    vids = list(steps.keys())
    # Build claim proposals for first feasible task if any
    from race_casablanca.marl.env import OP_DEFER

    base = {vid: (0, COMM_SUPPRESS) for vid in vids}
    # Run once
    env2 = _env(ABLATION_A, max_decisions=5)
    s2 = env2.reset(seed=7)
    # Reverse action dict order
    rev = {vid: base[vid] for vid in reversed(vids)}
    fwd = {vid: base[vid] for vid in vids}
    env.step(fwd)
    env2.step(rev)
    own1 = {vid: list(env.sim.vehicles[vid].committed) for vid in vids}
    own2 = {vid: list(env2.sim.vehicles[vid].committed) for vid in vids}
    assert own1 == own2


def test_random_matched_uses_predeclared_p():
    env = _env(ABLATION_C, matched_send_p=0.25)
    assert abs(env.matched_send_p - 0.25) < 1e-9
    assert env.comm_externally_controlled is True
