"""Energy-certified task-specific bids for RACE-COMM (non-learning)."""

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
    charge_burden_s: float
    as_of_s: float
    expires_s: float
    reason: str = ""

    def to_payload(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_payload(payload: dict) -> "TaskBid":
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
            reason=str(payload.get("reason", "")),
        )

    def is_fresh(self, now_s: float) -> bool:
        return now_s <= self.expires_s + 1e-9

    def payload_bytes(self) -> int:
        return len(json.dumps(self.to_payload(), separators=(",", ":")).encode("utf-8"))


def bid_sort_key(bid: TaskBid) -> tuple:
    """Lower is better. Infeasible bids sort last."""

    if not bid.feasible:
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
) -> TaskBid:
    """Build a bid from local feasibility only (no peer truth)."""

    chk: FeasibilityCheck = actions.check_insertion(obs.vehicle_id, task.request_id)
    travel = float(chk.marginal_travel_s or chk.added_travel_s or 0.0)
    return TaskBid(
        request_id=task.request_id,
        sender_id=obs.vehicle_id,
        feasible=bool(chk.feasible),
        marginal_travel_s=travel,
        marginal_energy_kwh=float(chk.marginal_energy_kwh or 0.0),
        energy_flex_kwh=float(chk.energy_flex_kwh or 0.0),
        deadline_slack_s=float(chk.min_deadline_slack_s or 0.0),
        charge_burden_s=0.0,
        as_of_s=float(obs.now_s),
        expires_s=float(obs.now_s) + float(ttl_s),
        reason=str(chk.reason or ""),
    )


def best_bid(bids: Iterable[TaskBid]) -> TaskBid | None:
    ranked = sorted(bids, key=bid_sort_key)
    return ranked[0] if ranked else None


def self_should_claim(own: TaskBid, peer_bids: Iterable[TaskBid]) -> bool:
    """True iff own feasible bid is uniquely best (or tied with own id winning)."""

    if not own.feasible:
        return False
    best = best_bid([own, *[b for b in peer_bids if b.feasible and b.is_fresh(own.as_of_s)]])
    return best is not None and best.sender_id == own.sender_id
