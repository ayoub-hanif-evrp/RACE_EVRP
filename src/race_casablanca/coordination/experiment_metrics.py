"""Canonical episode metric extraction for RACE development / frozen evaluations.

Maps simulator fields correctly (Prompt 2 fixes):
- energy from ``energy_consumed_kwh`` / ``energy_delivered_kwh`` (not total_energy_kwh)
- decision latency from ``mean_decision_runtime_s`` (convert to ms)
- communication: preferred primary cost is ``n_bid_attempted_bytes`` (includes drops)
"""

from __future__ import annotations

import json
from typing import Any


def extract_episode_row(
    *,
    sim: Any,
    policy: Any,
    metrics: dict[str, Any],
    scenario: str,
    treatment: str,
    delay_s: float,
    packet_loss_p: float,
    n_vehicles: int,
    soc: float,
    config_hash: str,
    wall_s: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    owners = {rid: req.owner for rid, req in sim.requests.items() if req.owner}
    mean_rt_s = float(metrics.get("mean_decision_runtime_s", 0.0) or 0.0)
    p50_s = float(metrics.get("p50_decision_runtime_s", 0.0) or 0.0)
    p95_s = float(metrics.get("p95_decision_runtime_s", 0.0) or 0.0)

    attempted_bytes = float(getattr(sim, "n_bid_attempted_bytes", 0) or 0)
    scheduled_bytes = float(getattr(sim, "n_bid_bytes", 0) or 0)
    if attempted_bytes <= 0 and scheduled_bytes > 0:
        # Backward compat if running older simulator without attempted counters.
        attempted_bytes = scheduled_bytes

    row = {
        "scenario": scenario,
        "treatment": treatment,
        "delay_s": float(delay_s),
        "packet_loss_p": float(packet_loss_p),
        "n_vehicles": int(n_vehicles),
        "initial_soc": float(soc),
        "config_hash": config_hash,
        "n_requests": float(metrics.get("n_requests", 0) or 0),
        "n_on_time": float(metrics.get("n_on_time", 0) or 0),
        "n_served": float(metrics.get("n_served", 0) or 0),
        "n_missed": float(metrics.get("n_missed", 0) or 0),
        "n_expired": float(metrics.get("n_expired", 0) or 0),
        "n_rejected": float(metrics.get("n_rejected", 0) or 0),
        "on_time_rate_all": float(metrics.get("on_time_rate_all", 0) or 0),
        "n_late_served": float(metrics.get("n_served", 0) or 0) - float(metrics.get("n_on_time", 0) or 0),
        "energy_consumed_kwh": float(metrics.get("energy_consumed_kwh", 0) or 0),
        "energy_delivered_kwh": float(metrics.get("energy_delivered_kwh", 0) or 0),
        "charge_duration_s": float(metrics.get("charge_duration_s", 0) or 0),
        "n_charges": float(metrics.get("n_charges", 0) or 0),
        "total_distance_m": float(metrics.get("total_distance_m", 0) or 0),
        "total_travel_s": float(metrics.get("total_travel_s", 0) or 0),
        "battery_reserve_violations": float(metrics.get("battery_reserve_violations", 0) or 0),
        "battery_exhaustion": float(metrics.get("battery_exhaustion", 0) or 0),
        "planned_energy_rejections": float(metrics.get("planned_energy_rejections", 0) or 0),
        "n_strandings": float(metrics.get("n_strandings", getattr(sim, "n_strandings", 0)) or 0),
        "mean_decision_runtime_s": mean_rt_s,
        "mean_decision_runtime_ms": 1000.0 * mean_rt_s,
        "p50_decision_runtime_ms": 1000.0 * p50_s,
        "p95_decision_runtime_ms": 1000.0 * p95_s,
        "n_decisions": float(metrics.get("n_decisions", 0) or 0),
        # Communication — primary cost = attempted recipient fan-out bytes.
        "n_bid_attempted_messages": float(getattr(sim, "n_bid_attempted_messages", 0) or 0),
        "n_bid_attempted_bytes": attempted_bytes,
        "n_bid_dropped_messages": float(getattr(sim, "n_bid_dropped_messages", 0) or 0),
        "n_bid_dropped_bytes": float(getattr(sim, "n_bid_dropped_bytes", 0) or 0),
        "n_bid_scheduled_messages": float(
            getattr(sim, "n_bid_scheduled_messages", getattr(sim, "n_bid_messages", 0)) or 0
        ),
        "n_bid_scheduled_bytes": scheduled_bytes,
        "n_bid_delivered_messages": float(getattr(sim, "n_bid_delivered_messages", 0) or 0),
        "n_bid_delivered_bytes": float(getattr(sim, "n_bid_delivered_bytes", 0) or 0),
        "n_bid_messages_legacy": float(getattr(sim, "n_bid_messages", 0) or 0),
        "n_bid_bytes_legacy": scheduled_bytes,
        "n_packets_dropped": float(getattr(sim, "n_packets_dropped", 0) or 0),
        "n_bid_delivers_superseded": float(getattr(sim, "n_bid_delivers_superseded", 0) or 0),
        "n_bid_delivers_coalesced": float(getattr(sim, "n_bid_delivers_coalesced", 0) or 0),
        "mean_assign_wait_s": (
            float(sim.sum_assign_wait_s) / float(sim.n_assign_windows)
            if getattr(sim, "n_assign_windows", 0)
            else 0.0
        ),
        "sum_assign_wait_s": float(getattr(sim, "sum_assign_wait_s", 0) or 0),
        "n_assign_deferred": float(getattr(sim, "n_assign_deferred", 0) or 0),
        "n_assign_immediate": float(getattr(sim, "n_assign_immediate", 0) or 0),
        "n_claims_attempted": float(getattr(policy, "n_claims_attempted", 0) or 0),
        "n_claims_success": float(getattr(policy, "n_claims_success", 0) or 0),
        "n_defers_to_peer": float(getattr(policy, "n_defers_to_peer", 0) or 0),
        "n_csc_safe_fallbacks": float(getattr(policy, "n_csc_safe_fallbacks", 0) or 0),
        "n_speculative_offers_ignored": float(getattr(policy, "n_speculative_offers_ignored", 0) or 0),
        "n_counterfactual_decision_changes": float(
            getattr(policy, "n_counterfactual_decision_changes", 0) or 0
        ),
        "n_registry_dup_rejects": float(getattr(sim.registry, "n_rejected_duplicates", 0) or 0),
        "wall_s": float(wall_s),
        "owners_json": json.dumps(owners, sort_keys=True),
    }
    if extra:
        row.update(extra)
    return row
