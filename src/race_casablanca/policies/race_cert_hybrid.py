"""RACE-CERT hybrid: frozen native cooperative routing + pluggable communication.

Routing / charging / claim logic is inherited unchanged from ``RaceCooperativePolicy``.
Only ``_maybe_communicate`` is specialized for certified / learned modes.
"""

from __future__ import annotations

from typing import Callable

from race_casablanca.coordination.certifying_protocol import certified_should_send
from race_casablanca.coordination.selective_protocol import BidMemory, selective_should_send
from race_casablanca.coordination.task_bids import TaskBid
from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.policy_api import ActionInterface, RestrictedObservation


# Signature: (own, peers, memory, now_s, feat_vec) -> (send: bool, kind: str)
LearnedSendFn = Callable[..., tuple[bool, str]]


class RaceCertHybridPolicy(RaceCooperativePolicy):
    """Same physical controller; communication modes include certified and learned."""

    name = "race_cert_hybrid"

    def __init__(
        self,
        comm_mode: str = "certified",
        *,
        learned_send_fn: LearnedSendFn | None = None,
        announce_peer_count: bool = True,
        **kwargs,
    ):
        allowed = {
            "none",
            "periodic",
            "full",
            "random",
            "selective",
            "random_matched",
            "certified",
            "learned",
        }
        # Parent validates a smaller set — set temporarily then override.
        mode = str(comm_mode)
        if mode not in allowed:
            raise ValueError(f"unknown comm_mode={mode}")
        parent_mode = mode if mode in {"none", "periodic", "full", "random", "selective", "random_matched"} else "selective"
        super().__init__(comm_mode=parent_mode, **kwargs)
        self.comm_mode = mode
        self.learned_send_fn = learned_send_fn
        self.announce_peer_count = bool(announce_peer_count)

        self.n_certified_resolutions = 0
        self.n_ambiguous_fallbacks = 0
        self.n_certified_suppress = 0
        self.n_learned_sends = 0
        self.n_learned_suppress = 0

    def _n_announced_peers(self, obs: RestrictedObservation) -> int:
        # Peers known in restricted view (may be empty under severe delay).
        return max(0, len(getattr(obs, "peers", {}) or {}))

    def _maybe_communicate(
        self,
        obs: RestrictedObservation,
        actions: ActionInterface,
        own_bids: dict[str, TaskBid],
        reason: str,
    ) -> None:
        if self.comm_mode in {"none", "periodic", "full", "random", "selective", "random_matched"}:
            return super()._maybe_communicate(obs, actions, own_bids, reason)

        candidates = list(own_bids.items())
        n_peers = self._n_announced_peers(obs) if self.announce_peer_count else None
        for rid, own in candidates:
            peers = self._peer_bids_for(obs, rid)
            key = (obs.vehicle_id, rid)
            mem = self._sent.get(key)
            send = False
            kind = "none"

            if self.comm_mode == "certified":
                send, kind, cert = certified_should_send(
                    own,
                    peers,
                    mem,
                    now_s=float(obs.now_s),
                    n_announced_peers=n_peers,
                )
                if cert.certified:
                    self.n_certified_resolutions += 1
                if kind == "ambiguous_fallback":
                    self.n_ambiguous_fallbacks += 1
                if kind == "certified_suppress":
                    self.n_certified_suppress += 1
            elif self.comm_mode == "learned":
                if self.learned_send_fn is None:
                    # Safe fallback: certified rule (never invent routing changes).
                    send, kind, cert = certified_should_send(
                        own, peers, mem, now_s=float(obs.now_s), n_announced_peers=n_peers
                    )
                else:
                    feat = self._comm_features(own, peers, mem, float(obs.now_s), n_peers)
                    send, kind = self.learned_send_fn(own, peers, mem, float(obs.now_s), feat)
                if send:
                    self.n_learned_sends += 1
                else:
                    self.n_learned_suppress += 1
            else:
                raise RuntimeError(f"unhandled comm_mode={self.comm_mode}")

            if not send:
                continue
            payload = own.to_payload()
            if kind == "withdraw":
                payload["feasible"] = False
                payload["withdrawn"] = True
                self.n_withdrawals += 1
            if self.comm_mode == "certified":
                payload["race_mechanism"] = "decision_certifying_heuristic_v1"
            nbytes = actions.broadcast_task_bid(obs.vehicle_id, payload)
            self.n_messages_sent_by_policy += 1
            self.n_bid_bytes_sent += int(nbytes)
            self._sent[key] = BidMemory(bid=own, send_s=obs.now_s)

    @staticmethod
    def _comm_features(
        own: TaskBid,
        peers: list[TaskBid],
        mem: BidMemory | None,
        now_s: float,
        n_peers: int | None,
    ) -> list[float]:
        fresh = [b for b in peers if b.is_fresh(now_s)]
        best_peer = min((b.marginal_travel_s for b in fresh if b.feasible), default=1e6)
        return [
            1.0 if own.feasible else 0.0,
            float(own.marginal_travel_s),
            float(own.energy_flex_kwh),
            float(own.deadline_slack_s),
            float(len(fresh)),
            float(best_peer),
            float(now_s - mem.send_s) if mem is not None else 1e3,
            float(n_peers or 0),
            1.0 if mem is None else 0.0,
        ]


def make_hybrid(comm_mode: str, **kwargs) -> RaceCertHybridPolicy | RaceCooperativePolicy:
    """Factory: certified/learned → hybrid; classic modes → native cooperative."""

    if comm_mode in {"certified", "learned"}:
        return RaceCertHybridPolicy(comm_mode=comm_mode, **kwargs)
    return RaceCooperativePolicy(comm_mode=comm_mode, **kwargs)
