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


def event_triggered_should_send(
    own: TaskBid,
    peer_bids: list[TaskBid],
    memory: BidMemory | None,
    *,
    now_s: float,
) -> tuple[bool, str]:
    """Minimal event-triggered baseline: first feasible bid + material/invalidation only.

    No contest refresh and no near-expiry refresh — isolates whether selective's
    extra refresh rules matter beyond eliminating repeated full broadcasts.
    """

    if memory is None:
        if own.feasible:
            return True, "initial"
        if any(b.feasible and b.is_fresh(now_s) for b in peer_bids):
            return True, "withdraw"
        return False, "none"
    if material_change(memory.bid, own):
        if memory.bid.feasible and not own.feasible:
            return True, "withdraw"
        return True, "material_change"
    return False, "none"


@dataclass
class MatchedBudgetController:
    """Random sends until a fixed *recipient-transmission* budget is exhausted.

    ``broadcast_task_bid`` fans out to ``n_recipients`` peers. Each allow() that
    results in a send must charge ``n_recipients`` against the budget so that
    matching selective's ``n_bid_messages`` (recipient count) is apples-to-apples.
    """

    budget: int
    sent: int = 0  # recipient transmissions charged
    n_recipients: int = 1

    def allow(self, rng: random.Random, n_candidates: int) -> bool:
        if self.sent >= self.budget or n_candidates <= 0:
            return False
        cost = max(1, int(self.n_recipients))
        if self.sent + cost > self.budget:
            return False
        remaining_slots = max(1, n_candidates)
        remaining_budget_units = max(1, (self.budget - self.sent) // cost)
        p = min(1.0, remaining_budget_units / float(remaining_slots))
        if rng.random() < p:
            self.sent += cost
            return True
        return False


@dataclass
class MatchedByteBudgetController:
    """Random sends until a fixed *attempted recipient-byte* budget is exhausted.

    Cost is always ``actual_serialized_payload_bytes * n_recipients`` (fan-out),
    matching ``OnlineSimulator.broadcast_task_bid`` attempted-byte accounting.

    ``typical_payload_bytes`` is retained only as a fallback estimate when the
    caller cannot supply a measured payload size (legacy); prefer passing
    ``payload_bytes=``.
    """

    budget_bytes: float
    used_bytes: float = 0.0
    typical_payload_bytes: float = 400.0
    n_recipients: int = 1

    def fanout_cost(self, payload_bytes: float) -> float:
        return max(1.0, float(payload_bytes)) * max(1, int(self.n_recipients))

    def allow(
        self,
        rng: random.Random,
        n_candidates: int,
        *,
        payload_bytes: float | None = None,
    ) -> bool:
        if self.used_bytes >= self.budget_bytes - 1e-12 or n_candidates <= 0:
            return False
        unit = (
            float(payload_bytes)
            if payload_bytes is not None and float(payload_bytes) > 0
            else float(self.typical_payload_bytes)
        )
        cost = self.fanout_cost(unit)
        if self.used_bytes + cost > self.budget_bytes + 1e-9:
            return False
        remaining_slots = max(1, int(n_candidates))
        remaining_units = max(1.0, (self.budget_bytes - self.used_bytes) / cost)
        p = min(1.0, remaining_units / float(remaining_slots))
        if rng.random() < p:
            self.used_bytes += cost
            return True
        return False

    def remaining_bytes(self) -> float:
        return max(0.0, float(self.budget_bytes) - float(self.used_bytes))
