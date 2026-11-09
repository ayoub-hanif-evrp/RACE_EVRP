"""Selective / ablation communication controls for task-bid exchange."""

from __future__ import annotations

import random
from dataclasses import dataclass

from race_casablanca.coordination.task_bids import TaskBid, best_bid


@dataclass
class BidMemory:
    """Last bid *transmitted* by self for a request."""

    bid: TaskBid
    send_s: float


def material_change(
    prev: TaskBid,
    new: TaskBid,
    *,
    travel_tol_s: float = 30.0,
    energy_tol_kwh: float = 0.5,
) -> bool:
    if prev.feasible != new.feasible:
        return True
    if prev.commitment_version != new.commitment_version:
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
) -> tuple[bool, str]:
    """Return (send, kind) where kind ∈ {initial, material_change, contest, expiry_refresh, withdraw, none}.

    Near-expiry uses the *last transmitted* bid's expires_s (memory.bid), not the newly computed one.
    """

    if memory is None:
        if own.feasible:
            return True, "initial"
        if any(b.feasible and b.is_fresh(now_s) for b in peer_bids):
            return True, "withdraw"  # publish infeasible / withdraw interest
        return False, "none"

    if material_change(memory.bid, own):
        if memory.bid.feasible and not own.feasible:
            return True, "withdraw"
        return True, "material_change"

    fresh_peers = [b for b in peer_bids if b.is_fresh(now_s)]
    if own.feasible and fresh_peers:
        best = best_bid([own, *fresh_peers])
        if best is not None and best.sender_id != own.sender_id:
            # Peer winning — refresh only if *transmitted* certificate is near expiry
            if memory.bid.expires_s - now_s < refresh_before_expiry_s:
                return True, "contest"
        if best is not None and best.sender_id == own.sender_id:
            if now_s - memory.send_s > refresh_before_expiry_s:
                return True, "contest"

    # Expiry refresh against last *sent* certificate
    if own.feasible and (memory.bid.expires_s - now_s) < refresh_before_expiry_s:
        return True, "expiry_refresh"
    return False, "none"


def random_should_send(rng: random.Random, p_send: float) -> bool:
    return rng.random() < float(p_send)


@dataclass
class MatchedBudgetController:
    """Random sends until a fixed message budget is exhausted (matched to selective)."""

    budget: int
    sent: int = 0

    def allow(self, rng: random.Random, n_candidates: int) -> bool:
        if self.sent >= self.budget or n_candidates <= 0:
            return False
        remaining_slots = max(1, n_candidates)
        # Approximate uniform spend of remaining budget over remaining candidates
        p = min(1.0, (self.budget - self.sent) / float(remaining_slots))
        if rng.random() < p:
            self.sent += 1
            return True
        return False
