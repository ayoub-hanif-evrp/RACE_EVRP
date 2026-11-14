"""RACE hybrid: frozen native cooperative routing + pluggable communication.

Routing / charging / claim logic inherited from ``RaceCooperativePolicy``.
Communication modes: classic + certified + ecom + learned.
"""

from __future__ import annotations

from typing import Callable

from race_casablanca.coordination.certifying_protocol import certified_should_send
from race_casablanca.coordination.race_ecom import ecom_should_send, roster_competitor_count
from race_casablanca.coordination.selective_protocol import BidMemory
from race_casablanca.coordination.task_bids import TaskBid
from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.policy_api import ActionInterface, RestrictedObservation


LearnedSendFn = Callable[..., tuple[bool, str]]


class RaceCertHybridPolicy(RaceCooperativePolicy):
    name = "race_cert_hybrid"

    def __init__(
        self,
        comm_mode: str = "ecom",
        *,
        learned_send_fn: LearnedSendFn | None = None,
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
            "ecom",
            "learned",
        }
        mode = str(comm_mode)
        if mode not in allowed:
            raise ValueError(f"unknown comm_mode={mode}")
        parent_mode = (
            mode
            if mode in {"none", "periodic", "full", "random", "selective", "random_matched"}
            else "selective"
        )
        super().__init__(comm_mode=parent_mode, **kwargs)
        self.comm_mode = mode
        self.learned_send_fn = learned_send_fn

        self.n_certified_resolutions = 0
        self.n_ambiguous_fallbacks = 0
        self.n_certified_suppress = 0
        self.n_ecom_proved = 0
        self.n_ecom_heuristic = 0
        self.n_ecom_fallback = 0
        self.n_learned_sends = 0
        self.n_learned_suppress = 0

    def _competitor_count(self, obs: RestrictedObservation) -> int:
        roster = obs.fleet_vehicle_ids or ()
        if not roster:
            # Fail closed: unknown membership ⇒ treat as incomplete (many unknowns).
            return 10**9
        return roster_competitor_count(roster, obs.vehicle_id)

    def _maybe_communicate(
        self,
        obs: RestrictedObservation,
        actions: ActionInterface,
        own_bids: dict[str, TaskBid],
        reason: str,
    ) -> None:
        if self.comm_mode in {"none", "periodic", "full", "random", "selective", "random_matched"}:
            return super()._maybe_communicate(obs, actions, own_bids, reason)

        # Cascade guard (same rationale as full-comm): message deliveries update
        # local bid tables and may re-enter decide(); rebroadcasting here recreates
        # event floods under delay. Claims still run in decide(); communication is
        # reserved for release / exchange / assign / periodic / charge / idle.
        if reason == "message":
            return

        n_comp = self._competitor_count(obs)
        roster = obs.fleet_vehicle_ids or ()
        for rid, own in own_bids.items():
            peers = self._peer_bids_for(obs, rid)
            key = (obs.vehicle_id, rid)
            mem = self._sent.get(key)
            send = False
            kind = "none"

            if self.comm_mode == "certified":
                send, kind, cert = certified_should_send(
                    own, peers, mem, now_s=float(obs.now_s), n_announced_peers=n_comp
                )
                if cert.certified:
                    self.n_certified_resolutions += 1
                if kind == "ambiguous_fallback":
                    self.n_ambiguous_fallbacks += 1
                if kind == "certified_suppress":
                    self.n_certified_suppress += 1
            elif self.comm_mode == "ecom":
                dec = ecom_should_send(
                    own,
                    peers,
                    mem,
                    now_s=float(obs.now_s),
                    fleet_vehicle_ids=roster,
                )
                send, kind = dec.send, dec.kind
                if dec.status == "proved":
                    self.n_ecom_proved += 1
                    if dec.cert.certified:
                        self.n_certified_resolutions += 1
                elif dec.status == "heuristic":
                    self.n_ecom_heuristic += 1
                elif dec.status == "fallback":
                    self.n_ecom_fallback += 1
                if kind in {"proved_suppress", "await_coverage"}:
                    self.n_certified_suppress += 1
                if kind == "ambiguous_critical":
                    self.n_ambiguous_fallbacks += 1
            elif self.comm_mode == "learned":
                if self.learned_send_fn is None:
                    dec = ecom_should_send(
                        own, peers, mem, now_s=float(obs.now_s), fleet_vehicle_ids=roster
                    )
                    send, kind = dec.send, dec.kind
                else:
                    feat = self._comm_features(own, peers, mem, float(obs.now_s), n_comp)
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
            if self.comm_mode in {"certified", "ecom"}:
                payload["race_mechanism"] = (
                    "race_ecom_v1" if self.comm_mode == "ecom" else "decision_certifying_heuristic_v1"
                )
            nbytes = actions.broadcast_task_bid(obs.vehicle_id, payload)
            self.n_messages_sent_by_policy += 1
            self.n_bid_bytes_sent += int(nbytes)
            self._sent[key] = BidMemory(bid=own, send_s=obs.now_s)

    @staticmethod
    def _comm_features(own, peers, mem, now_s, n_peers) -> list[float]:
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
            float(n_peers if n_peers < 10**8 else -1),
            1.0 if mem is None else 0.0,
        ]


def make_hybrid(comm_mode: str, **kwargs) -> RaceCertHybridPolicy | RaceCooperativePolicy:
    if comm_mode in {"certified", "ecom", "learned"}:
        return RaceCertHybridPolicy(comm_mode=comm_mode, **kwargs)
    return RaceCooperativePolicy(comm_mode=comm_mode, **kwargs)
