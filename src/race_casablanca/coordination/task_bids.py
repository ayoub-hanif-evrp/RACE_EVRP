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
    # Commitment-safe coordination signals (distinct from cost offers).
    claim_intent: bool = False  # sender intends to attempt ownership
    owned: bool = False  # sender asserts successful registry ownership

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
            claim_intent=bool(payload.get("claim_intent", False)),
            owned=bool(payload.get("owned", False)),
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


def resolve_peer_trust_mode(
    *,
    peer_trust_mode: str | None = None,
    delay_aware_trust: bool = False,
) -> str:
    """Map policy flags to a concrete trust mode.

    Legacy ``delay_aware_trust=True`` without an explicit mode ⇒ broken ``delay_half``.
    """

    if peer_trust_mode is not None and str(peer_trust_mode) != "":
        return str(peer_trust_mode)
    if delay_aware_trust:
        return "delay_half"
    return "ttl"


def self_should_claim(
    own: TaskBid,
    peer_bids: Iterable[TaskBid],
    *,
    now_s: float | None = None,
    message_delay_s: float = 0.0,
    delay_aware_trust: bool = False,
    peer_trust_mode: str | None = None,
    ignore_peer_bids: bool = False,
    known_commitment_versions: dict[str, int] | None = None,
) -> bool:
    """True iff own feasible bid is best among trusted peers (or tied with own id)."""

    if not own.feasible or own.withdrawn:
        return False
    if ignore_peer_bids:
        return True
    t = float(own.as_of_s if now_s is None else now_s)
    mode = resolve_peer_trust_mode(
        peer_trust_mode=peer_trust_mode, delay_aware_trust=delay_aware_trust
    )
    fresh = [
        b
        for b in peer_bids
        if peer_bid_trustworthy(
            b,
            now_s=t,
            message_delay_s=float(message_delay_s),
            peer_trust_mode=mode,
            known_commitment_versions=known_commitment_versions,
        )
    ]
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
    """Legacy deadline-aware wait before assigning under delayed bids.

    Urgent tasks (slack < urgency_slack_s) wait 0. Otherwise wait up to
    ``1.25 * message_delay_s`` capped by max_wait_s and remaining slack.

    PASS-1 follow-up diagnosis: this rule can schedule waits that consume a large
    fraction of TW slack under 30–120 s delays. Prefer
    ``deadline_energy_assignment_wait_s`` for commit-now under tight slack.
    """

    slack = float(task.tw_end_s) - float(now_s)
    if slack <= urgency_slack_s:
        return 0.0
    if message_delay_s <= 1e-12:
        return 0.0
    wait = min(float(max_wait_s), float(message_delay_s) * 1.25, max(0.0, slack - urgency_slack_s))
    return float(wait)


def deadline_energy_assignment_wait_s(
    task: TaskAnnouncement,
    *,
    now_s: float,
    message_delay_s: float,
    max_wait_s: float = 60.0,
    urgency_slack_s: float = 180.0,
    local_feasible: bool = True,
    local_travel_s: float | None = None,
    n_roster_competitors: int = 0,
    n_fresh_peer_bids: int = 0,
    delay_slack_frac: float = 0.35,
) -> float:
    """Commit-now vs brief wait under delayed peer bids (EV / hard-TW aware).

    Prefer immediate assignment when:
    - delay is a large fraction of remaining TW slack;
    - local travel already burns most remaining slack;
    - roster has no competitors, or peer coverage is already complete;
    - local insertion is infeasible (nothing to coordinate).

    Otherwise wait at most ``min(delay, useful_slack, max_wait)`` — never ``1.25×delay``.
    """

    if message_delay_s <= 1e-12:
        return 0.0
    slack = float(task.tw_end_s) - float(now_s)
    if slack <= urgency_slack_s:
        return 0.0
    if not local_feasible:
        return 0.0
    if int(n_roster_competitors) <= 0:
        return 0.0
    if int(n_fresh_peer_bids) >= int(n_roster_competitors):
        return 0.0
    if float(message_delay_s) >= float(delay_slack_frac) * max(slack, 1.0):
        return 0.0
    travel = float(local_travel_s) if local_travel_s is not None else 0.0
    if travel + urgency_slack_s >= slack:
        return 0.0
    useful = max(0.0, slack - urgency_slack_s - travel)
    wait = min(float(max_wait_s), float(message_delay_s), useful)
    return float(wait)


def peer_bid_trustworthy(
    bid: TaskBid,
    *,
    now_s: float,
    message_delay_s: float = 0.0,
    max_trust_age_s: float | None = None,
    peer_trust_mode: str = "ttl_commitment",
    known_commitment_versions: dict[str, int] | None = None,
) -> bool:
    """Whether a peer bid may influence assignment ranking.

    Modes
    -----
    ``delay_half`` (BROKEN / historical H_CURRENT):
        Rejects if age > max(15, 0.5 * message_delay). Under deterministic
        delivery at send+delay, age ≥ delay > 0.5*delay, so **all** normally
        delivered delayed bids fail. Kept only for ablation.

    ``ttl`` / ``ttl_commitment`` (repaired):
        Transport latency alone does **not** invalidate a bid. Require
        feasible, not withdrawn, within certificate TTL (``is_fresh``).
        ``ttl_commitment`` also rejects if ``known_commitment_versions`` shows
        a newer commitment version for the sender than the bid carries.
    """

    if not bid.feasible or bid.withdrawn:
        return False
    if not bid.is_fresh(now_s):
        return False
    mode = str(peer_trust_mode or "ttl_commitment")
    if mode == "delay_half":
        age = max(0.0, float(now_s) - float(bid.as_of_s))
        if max_trust_age_s is None:
            max_trust_age_s = (
                max(15.0, 0.5 * float(message_delay_s)) if message_delay_s > 1e-12 else 1e9
            )
        return age <= float(max_trust_age_s)
    if mode in {"ttl", "ttl_commitment"}:
        if mode == "ttl_commitment" and known_commitment_versions is not None:
            known = known_commitment_versions.get(bid.sender_id)
            if known is not None and int(bid.commitment_version) < int(known):
                return False
        return True
    if mode == "none":
        return False
    raise ValueError(f"unknown peer_trust_mode={mode}")
