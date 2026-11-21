"""Phase 3: evaluate learned / teacher policies on conflict stress (A/B/C/F)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import torch

from race_casablanca.marl.bc import NativeBridgeTeacher
from race_casablanca.marl.env import (
    ABLATION_A,
    ABLATION_B,
    ABLATION_C,
    ABLATION_F,
    RaceMultiAgentEnv,
)
from race_casablanca.marl.episode_sampler import ProceduralEpisodeGenerator
from race_casablanca.marl.mappo import MAPPOTrainer
from race_casablanca.marl.seed_banks import episode_train_seed


def conflict_factory(
    *,
    master_seed: int = 0,
    n_vehicles: int = 3,
    energy_binding: bool = True,
) -> Callable[..., dict]:
    return regime_factory(
        regime="conflict_dense",
        master_seed=master_seed,
        n_vehicles=n_vehicles,
        energy_binding=energy_binding,
    )


def regime_factory(
    *,
    regime: str = "baseline",
    master_seed: int = 0,
    n_vehicles: int = 3,
    energy_binding: bool = False,
) -> Callable[..., dict]:
    gen = ProceduralEpisodeGenerator.from_release(load_network=True)

    def factory(seed: int = 0, n_vehicles: int = n_vehicles) -> dict:
        ep = int(seed)
        return gen.make_episode(
            regime=regime,
            seed=episode_train_seed(master_seed, ep + 5000),
            n_vehicles=n_vehicles,
            master_seed=master_seed,
            episode_index=ep,
            energy_binding=energy_binding,
        )

    return factory


def _rollout_metrics(env: RaceMultiAgentEnv) -> dict[str, float]:
    m = env.final_metrics()
    return {
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_served": float(m.get("n_served", 0)),
        "n_bid_messages": float(m.get("n_bid_messages", 0)),
        "n_bid_bytes": float(m.get("n_bid_bytes", 0)),
        "n_op_charge": float(m.get("n_op_charge", 0)),
        "n_missed_feasible_pickup": float(m.get("n_missed_feasible_pickup", 0)),
    }


def eval_teacher_intent_matched(
    *,
    n_episodes: int = 2,
    ablation: str = ABLATION_F,
    master_seed: int = 0,
    max_decisions: int = 2000,
) -> dict[str, Any]:
    factory = conflict_factory(master_seed=master_seed)
    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ablation,
        seed=master_seed,
        max_decisions=max_decisions,
        initial_soc=0.35,
        claim_resolve_mode="sequential_native",
    )
    teacher = NativeBridgeTeacher(mode="intent_matched")
    rows = []
    for ep in range(n_episodes):
        env.reset(seed=ep)
        teacher.reset()
        while True:
            steps = env.step(teacher.actions(env))
            if list(steps.values())[0].done:
                break
        rows.append(_rollout_metrics(env))
    return {
        "method": "teacher_intent_matched",
        "ablation": ablation,
        "mean_ot": float(sum(r["on_time_rate_all"] for r in rows) / max(1, len(rows))),
        "mean_bytes": float(sum(r["n_bid_bytes"] for r in rows) / max(1, len(rows))),
        "episodes": rows,
    }


def eval_checkpoint(
    checkpoint: Path | str,
    *,
    ablation: str,
    n_episodes: int = 2,
    master_seed: int = 0,
    max_decisions: int = 2000,
    regime: str = "conflict_dense",
    energy_binding: bool = False,
) -> dict[str, Any]:
    factory = regime_factory(
        regime=regime, master_seed=master_seed, energy_binding=energy_binding
    )
    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ablation,
        seed=master_seed,
        max_decisions=max_decisions,
        initial_soc=0.35,
        claim_resolve_mode="sequential_native",
    )
    trainer = MAPPOTrainer(env)
    trainer.load(Path(checkpoint))
    rows = []
    for ep in range(n_episodes):
        steps = env.reset(seed=ep)
        while True:
            actions = {}
            for vid, st in steps.items():
                o = torch.as_tensor(st.obs, dtype=torch.float32).unsqueeze(0)
                om = torch.as_tensor(st.op_mask, dtype=torch.float32).unsqueeze(0)
                cm = torch.as_tensor(st.comm_mask, dtype=torch.float32).unsqueeze(0)
                with torch.no_grad():
                    op_logits, comm_logits = trainer.actor(o, om, cm)
                actions[vid] = (
                    int(torch.argmax(op_logits, dim=-1).item()),
                    int(torch.argmax(comm_logits, dim=-1).item()),
                )
            steps = env.step(actions)
            if list(steps.values())[0].done:
                break
        rows.append(_rollout_metrics(env))
    return {
        "method": "checkpoint",
        "checkpoint": str(checkpoint).replace("\\", "/"),
        "ablation": ablation,
        "regime": regime,
        "energy_binding": bool(energy_binding),
        "mean_ot": float(sum(r["on_time_rate_all"] for r in rows) / max(1, len(rows))),
        "mean_bytes": float(sum(r["n_bid_bytes"] for r in rows) / max(1, len(rows))),
        "episodes": rows,
    }


ABLATION_SET = (ABLATION_A, ABLATION_B, ABLATION_C, ABLATION_F)


def _actor_rollout_metrics(
    env: RaceMultiAgentEnv,
    actor,
    *,
    n_episodes: int,
    master_seed: int,
    device,
) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    actor.eval()
    for ep in range(n_episodes):
        steps = env.reset(seed=ep + master_seed * 17)
        while True:
            actions = {}
            for vid, st in steps.items():
                o = torch.as_tensor(st.obs, dtype=torch.float32, device=device).unsqueeze(0)
                om = torch.as_tensor(st.op_mask, dtype=torch.float32, device=device).unsqueeze(0)
                cm = torch.as_tensor(st.comm_mask, dtype=torch.float32, device=device).unsqueeze(0)
                with torch.no_grad():
                    op_logits, comm_logits = actor(o, om, cm)
                actions[vid] = (
                    int(torch.argmax(op_logits, dim=-1).item()),
                    int(torch.argmax(comm_logits, dim=-1).item()),
                )
            steps = env.step(actions)
            if list(steps.values())[0].done:
                break
        rows.append(_rollout_metrics(env))
    return rows


def eval_teacher_execute_ceiling(
    *,
    n_episodes: int = 4,
    master_seed: int = 0,
    max_decisions: int = 2000,
    energy_binding: bool = False,
    regime: str = "baseline",
) -> dict[str, Any]:
    """Native teacher OT ceiling (ablation-invariant) on a procedural regime."""
    factory = regime_factory(
        regime=regime, master_seed=master_seed, energy_binding=energy_binding
    )
    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ABLATION_F,
        seed=master_seed,
        max_decisions=max_decisions,
        initial_soc=0.35,
        claim_resolve_mode="sequential_native",
    )
    # intent_matched = execute mutations + step preflight (G1-safe path).
    teacher = NativeBridgeTeacher(mode="intent_matched")
    rows = []
    for ep in range(n_episodes):
        env.reset(seed=ep)
        teacher.reset()
        while True:
            steps = env.step(teacher.actions(env))
            if list(steps.values())[0].done:
                break
        rows.append(_rollout_metrics(env))
    return {
        "method": "teacher_intent_matched_ceiling",
        "ablation": ABLATION_F,
        "regime": regime,
        "energy_binding": bool(energy_binding),
        "mean_ot": float(sum(r["on_time_rate_all"] for r in rows) / max(1, len(rows))),
        "mean_bytes": float(sum(r["n_bid_bytes"] for r in rows) / max(1, len(rows))),
        "episodes": rows,
        "n_episodes": n_episodes,
    }


def eval_bc_g2(
    *,
    bc_steps: int = 256,
    bc_epochs: int = 25,
    dagger_rounds: int = 1,
    n_eval_episodes: int = 4,
    master_seed: int = 0,
    max_decisions: int = 2000,
    energy_binding: bool = False,
    regime: str = "baseline",
    ablation: str = ABLATION_F,
    teacher_mean_ot: float | None = None,
    absolute_threshold: float = 0.78,
    relative_slack: float = 0.03,
) -> dict[str, Any]:
    """
    Gate G2 probe: BC(+DAgger) from native_execute → deterministic OT.

    Absolute target 0.78 applies on *baseline* / val mix (teacher ceiling high).
    On conflict/energy stress, use relative: BC ≥ teacher − relative_slack.
    """
    from race_casablanca.marl.bc import (
        behavior_clone,
        collect_bc_batch,
        dagger_aggregate,
        evaluate_bc_accuracy,
    )
    from race_casablanca.marl.mappo import MAPPOTrainer

    factory = regime_factory(
        regime=regime, master_seed=master_seed, energy_binding=energy_binding
    )
    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ablation,
        seed=master_seed,
        max_decisions=max_decisions,
        initial_soc=0.35,
        claim_resolve_mode="sequential_native",
    )
    trainer = MAPPOTrainer(env)
    batch = collect_bc_batch(
        env, n_steps=bc_steps, seed=master_seed + 50, teacher="native_execute"
    )
    losses = behavior_clone(
        trainer.actor, batch, epochs=bc_epochs, device=trainer.device
    )
    for r in range(max(0, dagger_rounds)):
        batch = dagger_aggregate(
            env,
            trainer.actor,
            n_steps=max(32, bc_steps // 2),
            seed=master_seed + 200 + r,
            device=trainer.device,
            prior_batch=batch,
            teacher="native_execute",
        )
        losses = behavior_clone(
            trainer.actor,
            batch,
            epochs=max(5, bc_epochs // 2),
            device=trainer.device,
        )
    bc_acc = evaluate_bc_accuracy(trainer.actor, batch, device=trainer.device)
    finite_losses = [x for x in losses if x == x and abs(x) != float("inf")]
    bc_acc["final_loss"] = float(finite_losses[-1]) if finite_losses else None
    rows = _actor_rollout_metrics(
        env,
        trainer.actor,
        n_episodes=n_eval_episodes,
        master_seed=master_seed,
        device=trainer.device,
    )
    mean_ot = float(sum(r["on_time_rate_all"] for r in rows) / max(1, len(rows)))
    abs_pass = bool(mean_ot >= absolute_threshold)
    rel_pass = None
    gap = None
    if teacher_mean_ot is not None:
        gap = float(mean_ot - float(teacher_mean_ot))
        rel_pass = bool(mean_ot + 1e-9 >= float(teacher_mean_ot) - relative_slack)
    # Absolute if comfortable ceiling; else relative when teacher provided.
    g2_pass = abs_pass if teacher_mean_ot is None else bool(rel_pass)
    return {
        "method": "bc_native_execute",
        "ablation": ablation,
        "regime": regime,
        "energy_binding": bool(energy_binding),
        "mean_ot": mean_ot,
        "g2_pass": g2_pass,
        "g2_absolute_pass": abs_pass,
        "g2_relative_pass": rel_pass,
        "g2_threshold": absolute_threshold,
        "g2_relative_slack": relative_slack,
        "teacher_mean_ot": teacher_mean_ot,
        "ot_gap_vs_teacher": gap,
        "mean_bytes": float(sum(r["n_bid_bytes"] for r in rows) / max(1, len(rows))),
        "bc": bc_acc,
        "episodes": rows,
        "bc_steps": bc_steps,
        "bc_epochs": bc_epochs,
        "dagger_rounds": dagger_rounds,
        "n_eval_episodes": n_eval_episodes,
    }
