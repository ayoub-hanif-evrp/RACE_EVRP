"""Energy-certified task-specific bids for RACE-COMM (non-learning + MARL features).

Soft ranking is travel-primary with energy/slack as secondary keys — NOT a joint
energy-optimizing objective. Hard conservative feasibility remains a separate gate.
``charge_burden_s`` is omitted from ranking (always reported as 0 in v1) because the
depot charge model does not yet expose a defensible marginal charge-time delta per
candidate insertion without speculative future SOC targets.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Iterable

from race_casablanca.sim.feasibility_check import FeasibilityCheck
from race_casablanca.sim.policy_api import ActionInterface, RestrictedObservation, TaskAnnouncement


DEFAULT_BID_TTL_S = 180.0
BID_KIND = "task_bid"


@dataclass(frozen=True)
class TaskBid:
    request_id: str
    sender_id: str
    feasible: bool
    marginal_travel_s: float
    marginal_energy_kwh: float
    energy_flex_kwh: float
    deadline_slack_s: float
    charge_burden_s: float  # informational; not used in bid_sort_key (see module docstring)
    as_of_s: float
    expires_s: float
    seq: int = 0
    commitment_version: int = 0
    reason: str = ""
    withdrawn: bool = False
    # Optional travel-cost certificate interval (seconds). Absent → derive at ingest.
    cost_L_s: float | None = None
    cost_U_s: float | None = None
    race_cert: str = ""  # e.g. heuristic_interval_v1

    def to_payload(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_payload(payload: dict) -> "TaskBid":
        def _opt_float(key: str) -> float | None:
            if key not in payload or payload[key] is None:
                return None
            return float(payload[key])

        return TaskBid(
            request_id=str(payload["request_id"]),
            sender_id=str(payload["sender_id"]),
            feasible=bool(payload["feasible"]),
            marginal_travel_s=float(payload.get("marginal_travel_s", 0.0)),
            marginal_energy_kwh=float(payload.get("marginal_energy_kwh", 0.0)),
            energy_flex_kwh=float(payload.get("energy_flex_kwh", 0.0)),
            deadline_slack_s=float(payload.get("deadline_slack_s", 0.0)),
            charge_burden_s=float(payload.get("charge_burden_s", 0.0)),
            as_of_s=float(payload["as_of_s"]),
            expires_s=float(payload["expires_s"]),
            seq=int(payload.get("seq", 0)),
            commitment_version=int(payload.get("commitment_version", 0)),
            reason=str(payload.get("reason", "")),
            withdrawn=bool(payload.get("withdrawn", False)),
            cost_L_s=_opt_float("cost_L_s"),
            cost_U_s=_opt_float("cost_U_s"),
            race_cert=str(payload.get("race_cert", "")),
        )

    def is_fresh(self, now_s: float) -> bool:
        if self.withdrawn:
            return False
        return now_s <= self.expires_s + 1e-9

    def payload_bytes(self) -> int:
        return len(json.dumps(self.to_payload(), separators=(",", ":")).encode("utf-8"))


def bid_sort_key(bid: TaskBid) -> tuple:
    """Travel-primary soft ranking. Energy/slack are tie-breakers only.

    Hard energy feasibility is enforced upstream (infeasible bids sorted last).
    """

    if not bid.feasible or bid.withdrawn:
        return (1, float("inf"), float("inf"), float("inf"), bid.sender_id)
    return (
        0,
        float(bid.marginal_travel_s),
        -float(bid.energy_flex_kwh),
        -float(bid.deadline_slack_s),
        bid.sender_id,
    )


def compute_self_bid(
    obs: RestrictedObservation,
    actions: ActionInterface,
    task: TaskAnnouncement,
    *,
    ttl_s: float = DEFAULT_BID_TTL_S,
    seq: int = 0,
    commitment_version: int = 0,
) -> TaskBid:
    """Build a bid from local feasibility only (no peer truth)."""

    chk: FeasibilityCheck = actions.check_insertion(obs.vehicle_id, task.request_id)
    travel = float(chk.marginal_travel_s or chk.added_travel_s or 0.0)
    feas = bool(chk.feasible)
    return TaskBid(
        request_id=task.request_id,
        sender_id=obs.vehicle_id,
        feasible=feas,
        marginal_travel_s=travel,
        marginal_energy_kwh=float(chk.marginal_energy_kwh or 0.0),
        energy_flex_kwh=float(chk.energy_flex_kwh or 0.0),
        deadline_slack_s=float(chk.min_deadline_slack_s or 0.0),
        charge_burden_s=0.0,  # not ranked; see module docstring
        as_of_s=float(obs.now_s),
        expires_s=float(obs.now_s) + float(ttl_s),
        seq=int(seq),
        commitment_version=int(commitment_version),
        reason=str(chk.reason or ""),
        withdrawn=False,
        # Self certificate is a point interval under current commitments (A2).
        cost_L_s=travel if feas else None,
        cost_U_s=travel if feas else None,
        race_cert="heuristic_interval_v1" if feas else "",
    )


def best_bid(bids: Iterable[TaskBid]) -> TaskBid | None:
    ranked = sorted(bids, key=bid_sort_key)
    return ranked[0] if ranked else None


def self_should_claim(own: TaskBid, peer_bids: Iterable[TaskBid], *, now_s: float | None = None) -> bool:
    """True iff own feasible bid is best among fresh peers (or tied with own id)."""

    if not own.feasible or own.withdrawn:
        return False
    t = float(own.as_of_s if now_s is None else now_s)
    fresh = [b for b in peer_bids if b.feasible and b.is_fresh(t)]
    best = best_bid([own, *fresh])
    return best is not None and best.sender_id == own.sender_id


def assignment_wait_s(
    task: TaskAnnouncement,
    *,
    now_s: float,
    message_delay_s: float,
    max_wait_s: float = 120.0,
    urgency_slack_s: float = 180.0,
) -> float:
    """Deadline-aware wait before assigning under delayed bids.

    Urgent tasks (slack < urgency_slack_s) wait 0. Otherwise wait up to
    max(message_delay_s, small epsilon) capped by max_wait_s and remaining slack.
    """

    slack = float(task.tw_end_s) - float(now_s)
    if slack <= urgency_slack_s:
        return 0.0
    if message_delay_s <= 1e-12:
        return 0.0
    wait = min(float(max_wait_s), float(message_delay_s) * 1.25, max(0.0, slack - urgency_slack_s))
    return float(wait)
