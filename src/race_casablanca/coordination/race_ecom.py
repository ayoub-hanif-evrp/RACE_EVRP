"""RACE-ECOM: decision-critical energy-feasible communication under irreversible commitments.

Distinct from ``selective_should_send``: messages are sent only when they can change
the travel-primary winner under a public fleet roster, resolve incomplete coverage,
or refresh a near-expiry certificate that currently determines ownership intent.

Certification status (never conflated):
  A. PROVED — valid dominance under complete roster coverage + declared intervals
  B. HEURISTIC — choice under incomplete/aged information (explicit)
  C. FALLBACK — safe detailed bid exchange without certification

Aging wideners remain **heuristic** (see certifying_protocol). Incomplete roster
coverage ⇒ unknown competitors ⇒ not PROVED.
"""

from __future__ import annotations

from dataclasses import dataclass

from race_casablanca.coordination.certifying_protocol import (
    CertificationResult,
    certify_assignment,
)
from race_casablanca.coordination.selective_protocol import BidMemory, material_change
from race_casablanca.coordination.task_bids import TaskBid, best_bid, bid_sort_key


@dataclass(frozen=True)
class EcomDecision:
    send: bool
    kind: str
    status: str  # proved | heuristic | fallback | suppress
    cert: CertificationResult


def roster_competitor_count(fleet_vehicle_ids: tuple[str, ...] | list[str], self_id: str) -> int:
    return max(0, len(fleet_vehicle_ids) - (1 if self_id in fleet_vehicle_ids else 0))


def ecom_should_send(
    own: TaskBid,
    peer_bids: list[TaskBid],
    memory: BidMemory | None,
    *,
    now_s: float,
    fleet_vehicle_ids: tuple[str, ...] | list[str],
    refresh_before_expiry_s: float = 45.0,
) -> EcomDecision:
    """Decision-critical send gate using public roster coverage."""

    n_comp = roster_competitor_count(tuple(fleet_vehicle_ids), own.sender_id)
    cert = certify_assignment(
        own, peer_bids, now_s=now_s, n_announced_peers=n_comp
    )

    # --- Initial representation ---
    if memory is None:
        if own.feasible:
            # Must represent self among roster; incomplete until all speak or timeout.
            status = "fallback" if n_comp > 0 else "proved"
            return EcomDecision(True, "initial", status, cert)
        if any(b.feasible and b.is_fresh(now_s) for b in peer_bids):
            return EcomDecision(True, "withdraw", "fallback", cert)
        return EcomDecision(False, "none", "suppress", cert)

    if material_change(memory.bid, own):
        if memory.bid.feasible and not own.feasible:
            return EcomDecision(True, "withdraw", "fallback", cert)
        # Material change can alter winner → decision-critical
        return EcomDecision(True, "material_change", "fallback", cert)

    if not own.feasible:
        return EcomDecision(False, "none", "suppress", cert)

    # --- Incomplete coverage: unknown competitors (B/C, never A) ---
    if cert.reason == "incomplete_peer_coverage":
        # Do not expiry-chatter while coverage is incomplete — that recreates
        # delayed-message floods. Wait for peers / assignment deadline path.
        # One slow refresh only if the last send is already stale by a full TTL window.
        if now_s - memory.send_s >= max(refresh_before_expiry_s * 2.0, 90.0):
            return EcomDecision(True, "coverage_refresh", "fallback", cert)
        return EcomDecision(False, "await_coverage", "heuristic", cert)

    # --- PROVED unique winner ---
    if cert.certified and cert.winner_id is not None:
        if cert.winner_id == own.sender_id:
            if memory.bid.expires_s - now_s < refresh_before_expiry_s:
                return EcomDecision(True, "proved_winner_refresh", "proved", cert)
            return EcomDecision(False, "proved_suppress", "proved", cert)
        # Certified loser: message cannot change travel-primary winner under assumptions
        return EcomDecision(False, "proved_suppress", "proved", cert)

    # --- Ambiguous among represented set: could change winner ---
    fresh = [b for b in peer_bids if b.is_fresh(now_s) and b.feasible]
    ranking = best_bid([own, *fresh]) if own.feasible else None
    own_best = ranking is not None and ranking.sender_id == own.sender_id
    # Send if we are in the ambiguous band OR we currently look like the winner
    # but peers lack a tight certificate (heuristic).
    if own.sender_id in cert.ambiguous_ids or own_best:
        if now_s - memory.send_s < 5.0:
            return EcomDecision(False, "ambiguous_rate_limit", "heuristic", cert)
        return EcomDecision(True, "ambiguous_critical", "heuristic", cert)

    if own.feasible and (memory.bid.expires_s - now_s) < refresh_before_expiry_s:
        return EcomDecision(True, "expiry_refresh", "fallback", cert)
    return EcomDecision(False, "none", "suppress", cert)


def ecom_could_change_winner(
    own: TaskBid,
    peer_bids: list[TaskBid],
    *,
    now_s: float,
) -> bool:
    """True if omitting own bid would change the local travel-primary ranking."""

    fresh = [b for b in peer_bids if b.is_fresh(now_s)]
    with_own = best_bid([own, *fresh]) if own.feasible else best_bid(fresh)
    without = best_bid(fresh)
    if with_own is None and without is None:
        return False
    if with_own is None or without is None:
        return True
    return with_own.sender_id != without.sender_id
