"""Decision-certifying communication for travel-primary assignment costs.

Status: **heuristic / conditional** — not a general theorem under arbitrary
stale peer certificates. We document assumptions explicitly.

Assumptions (A1–A4)
--------------------
A1. Allocation score for ranking is ``marginal_travel_s`` (lower better), matching
    ``bid_sort_key`` primary key. Energy/slack remain soft tie-breakers only.
A2. A vehicle's *self* cost, when freshly computed from ``check_insertion``, is
    treated as a point interval ``[c, c]`` (exact under current commitments).
A3. A *peer* certificate of age ``Δ`` is widened to
    ``[c - w(Δ), c + w(Δ)]`` with ``w(Δ) = α·Δ + β`` (seconds of travel-cost
    uncertainty). This is a **declared heuristic** widening, not a proved
    Lipschitz bound on Casablanca travel times.
A4. Certification is only among the set of represented candidates (self + fresh
    peer payloads). Missing silent vehicles are treated as unknown; if any
    announced peer has no certificate, the local view is **non-certified** and
    the protocol falls back to requesting/sending detailed bids.

Conditional proposition (informal)
----------------------------------
Under A1–A4, if every eligible competitor is represented by a fresh interval and
``U_j < min_{i≠j} L_i``, then vehicle ``j`` has the uniquely lowest travel-primary
allocation cost among that represented set. Detailed further bids cannot change
the travel-primary ranking *within that set* without violating a peer's interval.
Physics is still re-checked at commitment time.
"""

from __future__ import annotations

from dataclasses import dataclass

from race_casablanca.coordination.selective_protocol import BidMemory, material_change
from race_casablanca.coordination.task_bids import TaskBid


# Heuristic aging wideners (seconds of travel-cost uncertainty).
AGE_SLOPE_S = 0.15  # per second of message age
AGE_INTERCEPT_S = 5.0
MAX_WIDEN_S = 180.0


@dataclass(frozen=True)
class CostInterval:
    sender_id: str
    L: float
    U: float
    cost_point: float
    age_s: float
    feasible: bool
    certified_source: str  # self_exact | peer_heuristic | infeasible


@dataclass(frozen=True)
class CertificationResult:
    certified: bool
    winner_id: str | None
    ambiguous_ids: tuple[str, ...]
    reason: str
    intervals: tuple[CostInterval, ...]


def widen_for_age(age_s: float) -> float:
    a = max(0.0, float(age_s))
    return float(min(MAX_WIDEN_S, AGE_INTERCEPT_S + AGE_SLOPE_S * a))


def interval_from_bid(bid: TaskBid, *, now_s: float, is_self: bool) -> CostInterval:
    if not bid.feasible or bid.withdrawn:
        return CostInterval(
            sender_id=bid.sender_id,
            L=float("inf"),
            U=float("inf"),
            cost_point=float("inf"),
            age_s=max(0.0, float(now_s) - float(bid.as_of_s)),
            feasible=False,
            certified_source="infeasible",
        )
    c = float(bid.marginal_travel_s)
    age = max(0.0, float(now_s) - float(bid.as_of_s))
    if is_self:
        return CostInterval(
            sender_id=bid.sender_id,
            L=c,
            U=c,
            cost_point=c,
            age_s=age,
            feasible=True,
            certified_source="self_exact",
        )
    w = widen_for_age(age)
    return CostInterval(
        sender_id=bid.sender_id,
        L=max(0.0, c - w),
        U=c + w,
        cost_point=c,
        age_s=age,
        feasible=True,
        certified_source="peer_heuristic",
    )


def certify_assignment(
    own: TaskBid,
    peer_bids: list[TaskBid],
    *,
    now_s: float,
    n_announced_peers: int | None = None,
) -> CertificationResult:
    """Return whether travel-primary winner is unambiguous under heuristic intervals.

    If ``n_announced_peers`` is provided and exceeds the number of fresh peer
    certificates, the view is incomplete → not certified (fallback).
    """

    fresh_peers = [b for b in peer_bids if b.is_fresh(now_s)]
    if n_announced_peers is not None and int(n_announced_peers) > len(fresh_peers):
        intervals = (
            interval_from_bid(own, now_s=now_s, is_self=True),
            *[interval_from_bid(b, now_s=now_s, is_self=False) for b in fresh_peers],
        )
        return CertificationResult(
            certified=False,
            winner_id=None,
            ambiguous_ids=tuple(sorted({own.sender_id, *[b.sender_id for b in fresh_peers]})),
            reason="incomplete_peer_coverage",
            intervals=intervals,
        )

    intervals = [
        interval_from_bid(own, now_s=now_s, is_self=True),
        *[interval_from_bid(b, now_s=now_s, is_self=False) for b in fresh_peers],
    ]
    feasible = [iv for iv in intervals if iv.feasible]
    if not feasible:
        return CertificationResult(
            False, None, tuple(), "no_feasible_candidate", tuple(intervals)
        )
    if len(feasible) == 1:
        only = feasible[0]
        return CertificationResult(
            True, only.sender_id, tuple(), "singleton_feasible", tuple(intervals)
        )

    # Find candidate with U_j < min_{i≠j} L_i
    for j in feasible:
        others = [iv for iv in feasible if iv.sender_id != j.sender_id]
        min_other_L = min(iv.L for iv in others)
        if j.U < min_other_L - 1e-9:
            return CertificationResult(
                True,
                j.sender_id,
                tuple(),
                "interval_dominance",
                tuple(intervals),
            )

    # Ambiguous: all feasible senders whose intervals overlap the current best L band
    best_L = min(iv.L for iv in feasible)
    best_U = min(iv.U for iv in feasible)
    ambiguous = tuple(
        sorted(iv.sender_id for iv in feasible if iv.L <= best_U + 1e-9 or iv.U >= best_L - 1e-9)
    )
    return CertificationResult(
        False, None, ambiguous, "overlapping_intervals", tuple(intervals)
    )


def certified_should_send(
    own: TaskBid,
    peer_bids: list[TaskBid],
    memory: BidMemory | None,
    *,
    now_s: float,
    n_announced_peers: int | None = None,
    refresh_before_expiry_s: float = 45.0,
) -> tuple[bool, str, CertificationResult]:
    """Certified-selective send gate. Routing/claim logic is unchanged elsewhere."""

    cert = certify_assignment(own, peer_bids, now_s=now_s, n_announced_peers=n_announced_peers)

    if memory is None:
        if own.feasible:
            return True, "initial", cert
        if any(b.feasible and b.is_fresh(now_s) for b in peer_bids):
            return True, "withdraw", cert
        return False, "none", cert

    if material_change(memory.bid, own):
        if memory.bid.feasible and not own.feasible:
            return True, "withdraw", cert
        return True, "material_change", cert

    if not own.feasible:
        return False, "none", cert

    if cert.certified:
        # Winner unambiguous among represented set — suppress unless we are winner
        # and our transmitted cert is near expiry.
        if cert.winner_id == own.sender_id:
            if memory.bid.expires_s - now_s < refresh_before_expiry_s:
                return True, "certified_winner_refresh", cert
            return False, "certified_suppress", cert
        # Loser under certification: no need to re-broadcast
        return False, "certified_suppress", cert

    # Ambiguous / incomplete → request-by-sending (fallback detailed bid)
    if own.sender_id in cert.ambiguous_ids or cert.reason in (
        "incomplete_peer_coverage",
        "overlapping_intervals",
    ):
        if now_s - memory.send_s < 5.0 and not material_change(memory.bid, own):
            # light rate-limit when we just sent
            return False, "ambiguous_rate_limit", cert
        return True, "ambiguous_fallback", cert

    if own.feasible and (memory.bid.expires_s - now_s) < refresh_before_expiry_s:
        return True, "expiry_refresh", cert
    return False, "none", cert
