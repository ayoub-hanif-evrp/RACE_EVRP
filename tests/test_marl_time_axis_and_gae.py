"""Numerical tests for time-indexed GAE (Gate 1)."""

from __future__ import annotations

import numpy as np

from race_casablanca.marl.buffer import FleetRolloutBuffer, compute_gae_time


def test_gae_ignores_extra_same_time_agents():
    """Adding a second simultaneous agent must not create an extra temporal discount step."""
    # Single-agent trajectory of length 2
    rewards = np.array([1.0, 1.0], dtype=np.float32)
    values = np.array([0.5, 0.5], dtype=np.float32)
    dones = np.array([0.0, 1.0], dtype=np.float32)
    truncs = np.array([0.0, 0.0], dtype=np.float32)
    adv1, ret1 = compute_gae_time(rewards, values, dones, truncs, last_value=0.0, gamma=0.99, lam=1.0)

    # Fleet buffer with 2 agents sharing the same team reward / value each time
    buf = FleetRolloutBuffer()
    for t in range(2):
        obs = np.zeros((2, 4), dtype=np.float32)
        buf.add(
            obs,
            obs.reshape(-1),
            op_actions=np.array([0, 0]),
            comm_actions=np.array([0, 0]),
            op_logprobs=np.array([0.0, 0.0]),
            comm_logprobs=np.array([0.0, 0.0]),
            reward=float(rewards[t]),
            done=float(dones[t]),
            trunc=0.0,
            value=float(values[t]),
            op_masks=np.ones((2, 2), dtype=np.float32),
            comm_masks=np.ones((2, 2), dtype=np.float32),
            elapsed=1.0,
        )
    adv_t, ret_t, adv_flat, _ = buf.compute_gae(0.0, gamma=0.99, lam=1.0, time_aware=False)
    assert adv_t.shape == (2,)
    assert np.allclose(adv_t, adv1, atol=1e-5)
    assert np.allclose(ret_t, ret1, atol=1e-5)
    # Flat advantages are broadcast copies, not temporally chained across agents
    assert adv_flat.shape == (4,)
    assert np.allclose(adv_flat[0], adv_flat[1])
    assert np.allclose(adv_flat[2], adv_flat[3])


def test_gae_independent_calculation():
    rewards = np.array([1.0, 0.0, 2.0], dtype=np.float32)
    values = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    dones = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    truncs = np.zeros(3, dtype=np.float32)
    gamma, lam = 0.9, 0.95
    adv, ret = compute_gae_time(rewards, values, dones, truncs, 0.0, gamma=gamma, lam=lam)
    # Hand calculation with V=0, last done:
    # t=2: delta=2, gae=2
    # t=1: delta=0, gae=0 + gamma*lam*2
    # t=0: delta=1, gae=1 + gamma*lam*(gamma*lam*2)
    gae2 = 2.0
    gae1 = 0.0 + gamma * lam * gae2
    gae0 = 1.0 + gamma * lam * gae1
    assert np.allclose(adv, [gae0, gae1, gae2], atol=1e-5)
    assert np.allclose(ret, adv + values, atol=1e-5)


def test_truncation_bootstraps_but_done_does_not():
    rewards = np.array([1.0], dtype=np.float32)
    values = np.array([0.5], dtype=np.float32)
    # Truncated: bootstrap last_value=10
    adv_tr, _ = compute_gae_time(
        rewards, values, dones=np.array([0.0]), truncs=np.array([1.0]), last_value=10.0, gamma=1.0, lam=1.0
    )
    assert np.allclose(adv_tr, [1.0 + 10.0 - 0.5], atol=1e-5)
    # Done: no bootstrap
    adv_done, _ = compute_gae_time(
        rewards, values, dones=np.array([1.0]), truncs=np.array([0.0]), last_value=10.0, gamma=1.0, lam=1.0
    )
    assert np.allclose(adv_done, [1.0 - 0.5], atol=1e-5)
