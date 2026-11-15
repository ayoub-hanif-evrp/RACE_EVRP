"""RACE-CSC: Commitment-Safe Coordination under nonbinding peer offers.

Core principle: a peer's lower-cost *offer* is not evidence they will claim or
complete the pickup. Defer only to credible commitment signals:

- ``owned=True`` (peer asserts registry ownership), or
- ``claim_intent=True`` (peer announces intent to claim), still TTL-fresh.

At zero message delay, concurrent offers remain usable for ranking (instantaneous
exchange). Under positive delay, offer-only bids never trigger speculative deferral.

Notation
--------
- Offer: feasible bid without claim_intent / owned
- Claim intention: claim_intent=True message
- Confirmed ownership: registry accept (local) or owned=True peer message
- Physical service: execution after claim (not guaranteed by coordination)
"""

from __future__ import annotations

from race_casablanca.coordination.task_bids import (
    TaskBid,
    best_bid,
    peer_bid_trustworthy,
    resolve_peer_trust_mode,
)


def credible_peer_bids(
    peer_bids: list[TaskBid],
    *,
    now_s: float,
    message_delay_s: float = 0.0,
    peer_trust_mode: str | None = "ttl_commitment",
    delay_aware_trust: bool = False,
    known_commitment_versions: dict[str, int] | None = None,
) -> list[TaskBid]:
    """Peers that may block a local claim under CSC rules."""

    mode = resolve_peer_trust_mode(
        peer_trust_mode=peer_trust_mode, delay_aware_trust=delay_aware_trust
    )
    out: list[TaskBid] = []
    instantaneous = float(message_delay_s) <= 1e-12
    for b in peer_bids:
        if not peer_bid_trustworthy(
            b,
            now_s=now_s,
            message_delay_s=message_delay_s,
            peer_trust_mode=mode,
            known_commitment_versions=known_commitment_versions,
        ):
            continue
        owned = bool(getattr(b, "owned", False))
        intent = bool(getattr(b, "claim_intent", False))
        if owned or intent:
            out.append(b)
        elif instantaneous:
            # Zero-delay exchange: concurrent offers are simultaneous ranking evidence.
            out.append(b)
        # else: delayed offer-only → not credible; do not defer
    return out


def csc_should_claim(
    own: TaskBid,
    peer_bids: list[TaskBid],
    *,
    now_s: float,
    message_delay_s: float = 0.0,
    peer_trust_mode: str | None = "ttl_commitment",
    delay_aware_trust: bool = False,
    known_commitment_versions: dict[str, int] | None = None,
    ignore_peer_bids: bool = False,
) -> bool:
    """True iff own should attempt atomic claim under commitment-safe rules."""

    if not own.feasible or own.withdrawn:
        return False
    if ignore_peer_bids:
        return True
    credible = credible_peer_bids(
        peer_bids,
        now_s=now_s,
        message_delay_s=message_delay_s,
        peer_trust_mode=peer_trust_mode,
        delay_aware_trust=delay_aware_trust,
        known_commitment_versions=known_commitment_versions,
    )
    # If any peer asserts ownership, never conflict-claim.
    if any(bool(getattr(b, "owned", False)) for b in credible):
        return False
    best = best_bid([own, *credible])
    return best is not None and best.sender_id == own.sender_id
