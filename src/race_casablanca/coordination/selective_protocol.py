"""Selective / ablation communication controls for task-bid exchange."""

from __future__ import annotations

import random
from dataclasses import dataclass

from race_casablanca.coordination.task_bids import TaskBid


@dataclass
class BidMemory:
    """Last bid sent by self for a request (for change / TTL triggers)."""

    bid: TaskBid
    send_s: float


def material_change(prev: TaskBid, new: TaskBid, *, travel_tol_s: float = 30.0, energy_tol_kwh: float = 0.5) -> bool:
    if prev.feasible != new.feasible:
        return True
    if abs(prev.marginal_travel_s - new.marginal_travel_s) > travel_tol_s:
        return True
    if abs(prev.energy_flex_kwh - new.energy_flex_kwh) > energy_tol_kwh:
        return True
    if abs(prev.deadline_slack_s - new.deadline_slack_s) > travel_tol_s:
        return True
    return False


def selective_should_send(
    own: TaskBid,
    peer_bids: list[TaskBid],
    memory: BidMemory | None,
    *,
    now_s: float,
    refresh_before_expiry_s: float = 45.0,
) -> bool:
    """Decision-relevant send: new/changed own bid, contest, or near-expiry refresh."""

    if memory is None:
        # Announce feasible bids; also announce infeasible when peers appear interested
        if own.feasible:
            return True
        return any(b.feasible and b.is_fresh(now_s) for b in peer_bids)

    if material_change(memory.bid, own):
        return True

    # Contest: a peer currently ranks better while we are feasible
    from race_casablanca.coordination.task_bids import best_bid

    fresh_peers = [b for b in peer_bids if b.is_fresh(now_s)]
    if own.feasible and fresh_peers:
        best = best_bid([own, *fresh_peers])
        if best is not None and best.sender_id != own.sender_id:
            # Peer winning — still refresh if our certificate is stale-ish
            if own.expires_s - now_s < refresh_before_expiry_s:
                return True
        if best is not None and best.sender_id == own.sender_id:
            # We win — send if peers may not know (no recent send)
            if now_s - memory.send_s > refresh_before_expiry_s:
                return True

    if own.feasible and (own.expires_s - now_s) < refresh_before_expiry_s:
        return True
    return False


def random_should_send(rng: random.Random, p_send: float) -> bool:
    return rng.random() < float(p_send)
