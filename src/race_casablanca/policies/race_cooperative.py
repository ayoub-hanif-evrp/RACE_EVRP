"""RACE-COMM non-learning cooperative policy: energy-certified task bids + selective messaging.

Soft ranking is travel-primary (energy/slack tie-breakers). Hard feasibility is separate.
Restricted mode must not read live peer truth via ActionInterface.get_simulator().
"""

from __future__ import annotations

import random
from dataclasses import replace

from race_casablanca.coordination.selective_protocol import (
    BidMemory,
    MatchedBudgetController,
    selective_should_send,
)
from race_casablanca.coordination.task_bids import (
    TaskBid,
    assignment_wait_s,
    compute_self_bid,
    self_should_claim,
)
from race_casablanca.sim.policy_api import (
    ActionInterface,
    FullInfoObservation,
    RestrictedObservation,
    TaskAnnouncement,
)


class RaceCooperativePolicy:
    name = "race_cooperative"
    two_phase_bidding = True

    def __init__(
        self,
        comm_mode: str = "selective",
        *,
        bid_ttl_s: float = 180.0,
        random_p_send: float = 0.25,
        matched_message_budget: int | None = None,
        rng_seed: int = 0,
        charge_target_soc: float = 0.70,
        enable_readiness_charge: bool = True,
        max_assign_wait_s: float = 120.0,
        urgency_slack_s: float = 180.0,
    ):
        """comm_mode: none | periodic | full | random | selective | random_matched."""

        allowed = {"none", "periodic", "full", "random", "selective", "random_matched"}
        if comm_mode not in allowed:
            raise ValueError(f"unknown comm_mode={comm_mode}")
        self.comm_mode = comm_mode
        self.bid_ttl_s = float(bid_ttl_s)
        self.random_p_send = float(random_p_send)
        self.rng = random.Random(int(rng_seed))
        self.charge_target_soc = float(charge_target_soc)
        self.enable_readiness_charge = bool(enable_readiness_charge)
        self.max_assign_wait_s = float(max_assign_wait_s)
        self.urgency_slack_s = float(urgency_slack_s)
        self._matched = (
            MatchedBudgetController(budget=int(matched_message_budget))
            if matched_message_budget is not None
            else None
        )

        self.n_messages_sent_by_policy = 0
        self.n_bid_bytes_sent = 0
        self.n_claims_attempted = 0
        self.n_claims_success = 0
        self.n_defers_to_peer = 0
        self.n_message_driven_decision_invocations = 0
        self.n_counterfactual_decision_changes = 0
        self.n_withdrawals = 0
        self._sent: dict[tuple[str, str], BidMemory] = {}
        self._seq = 0
        self._commit_version: dict[str, int] = {}

    def assignment_wait_for_request(self, sim, request_id: str) -> float:
        req = sim.requests.get(request_id)
        if req is None:
            return 0.0
        task = TaskAnnouncement(
            req.request_id, req.snap_node, req.tw_start_s, req.tw_end_s, req.service_s, req.weight_kg
        )
        return assignment_wait_s(
            task,
            now_s=sim.now_s,
            message_delay_s=float(sim.config.message_delay_s),
            max_wait_s=self.max_assign_wait_s,
            urgency_slack_s=self.urgency_slack_s,
        )

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if not isinstance(obs, RestrictedObservation):
            return
        try:
            actions.get_simulator()
            raise RuntimeError("restricted RaceCooperativePolicy obtained live simulator access")
        except PermissionError:
            pass

        if reason in ("message", "bid_assign"):
            self.n_message_driven_decision_invocations += 1

        if self.enable_readiness_charge and reason in (
            "request_release",
            "bid_exchange",
            "bid_assign",
            "charge_end",
            "epoch",
            "periodic_broadcast",
        ):
            self._maybe_charge(obs, actions)

        cv = self._commit_version.get(obs.vehicle_id, 0)
        tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)
        own_bids: dict[str, TaskBid] = {}
        for task in tasks:
            self._seq += 1
            own_bids[task.request_id] = compute_self_bid(
                obs, actions, task, ttl_s=self.bid_ttl_s, seq=self._seq, commitment_version=cv
            )

        exchange_only = reason == "bid_exchange"
        assign_only = reason == "bid_assign"

        if self.comm_mode != "none" and not assign_only:
            self._maybe_communicate(obs, actions, own_bids, reason)

        if exchange_only:
            return

        if obs.peer_bids and reason in ("message", "bid_assign", "periodic_broadcast"):
            intended = self._intended_claim(obs, own_bids)
            intended_empty = self._intended_claim(replace(obs, peer_bids={}), own_bids)
            if intended != intended_empty:
                self.n_counterfactual_decision_changes += 1

        claimed = self._claim_pass(obs, actions, own_bids)
        if claimed:
            self._commit_version[obs.vehicle_id] = cv + 1
            # Invalidate stale self certificates for other open tasks after commitment change
            if self.comm_mode not in ("none",):
                self._send_commitment_invalidations(obs, actions, claimed)

    def _peer_bids_for(self, obs: RestrictedObservation, request_id: str) -> list[TaskBid]:
        out: list[TaskBid] = []
        for sender, payload in (obs.peer_bids.get(request_id) or {}).items():
            if sender == obs.vehicle_id:
                continue
            try:
                bid = TaskBid.from_payload(payload)
            except (KeyError, TypeError, ValueError):
                continue
            if bid.is_fresh(obs.now_s):
                out.append(bid)
        return out

    def _intended_claim(self, obs: RestrictedObservation, own_bids: dict[str, TaskBid]) -> str | None:
        for task in sorted(obs.announced, key=lambda t: t.tw_end_s):
            own = own_bids.get(task.request_id)
            if own is None or not own.feasible:
                continue
            peers = self._peer_bids_for(obs, task.request_id)
            if self_should_claim(own, peers, now_s=obs.now_s):
                return task.request_id
        return None

    def _maybe_communicate(
        self,
        obs: RestrictedObservation,
        actions: ActionInterface,
        own_bids: dict[str, TaskBid],
        reason: str,
    ) -> None:
        candidates = list(own_bids.items())
        for rid, own in candidates:
            peers = self._peer_bids_for(obs, rid)
            key = (obs.vehicle_id, rid)
            mem = self._sent.get(key)
            send = False
            kind = "none"
            if self.comm_mode == "full":
                send = True
                kind = "full"
            elif self.comm_mode == "periodic":
                send = reason == "periodic_broadcast"
                kind = "periodic"
            elif self.comm_mode == "random":
                send = self.rng.random() < self.random_p_send
                kind = "random"
            elif self.comm_mode == "random_matched":
                if self._matched is None:
                    send = False
                else:
                    send = self._matched.allow(self.rng, len(candidates))
                kind = "random_matched"
            elif self.comm_mode == "selective":
                send, kind = selective_should_send(own, peers, mem, now_s=obs.now_s)

            if not send:
                continue
            payload = own.to_payload()
            if kind == "withdraw":
                payload["feasible"] = False
                payload["withdrawn"] = True
                self.n_withdrawals += 1
            nbytes = actions.broadcast_task_bid(obs.vehicle_id, payload)
            self.n_messages_sent_by_policy += 1
            self.n_bid_bytes_sent += int(nbytes)
            self._sent[key] = BidMemory(bid=own, send_s=obs.now_s)

    def _send_commitment_invalidations(
        self, obs: RestrictedObservation, actions: ActionInterface, claimed_rid: str
    ) -> None:
        """After accepting a task, publish material updates for remaining announced tasks."""

        cv = self._commit_version.get(obs.vehicle_id, 0)
        for task in obs.announced:
            if task.request_id == claimed_rid:
                continue
            self._seq += 1
            bid = compute_self_bid(
                obs, actions, task, ttl_s=self.bid_ttl_s, seq=self._seq, commitment_version=cv
            )
            key = (obs.vehicle_id, task.request_id)
            mem = self._sent.get(key)
            if mem is None:
                continue
            # Only refresh if we previously advertised interest
            nbytes = actions.broadcast_task_bid(obs.vehicle_id, bid.to_payload())
            self.n_messages_sent_by_policy += 1
            self.n_bid_bytes_sent += int(nbytes)
            self._sent[key] = BidMemory(bid=bid, send_s=obs.now_s)

    def _claim_pass(
        self,
        obs: RestrictedObservation,
        actions: ActionInterface,
        own_bids: dict[str, TaskBid],
    ) -> str | None:
        for task in sorted(obs.announced, key=lambda t: t.tw_end_s):
            own = own_bids[task.request_id]
            if not own.feasible:
                if task.tw_end_s <= obs.now_s:
                    actions.reject_request(task.request_id)
                continue
            peers = self._peer_bids_for(obs, task.request_id)
            if not self_should_claim(own, peers, now_s=obs.now_s):
                self.n_defers_to_peer += 1
                continue
            self.n_claims_attempted += 1
            # Fresh safety check at commitment time (bid never bypasses physics).
            chk = actions.check_insertion(obs.vehicle_id, task.request_id)
            if not chk.feasible:
                continue
            if actions.claim_task(obs.vehicle_id, task.request_id):
                self.n_claims_success += 1
                return task.request_id
        return None

    def _maybe_charge(self, obs: RestrictedObservation, actions: ActionInterface) -> None:
        v = obs.self_state
        if v.busy or v.mode in ("SERVING", "CHARGING", "MOVING"):
            return
        bat = float(v.battery_kwh)
        target_kwh = self.charge_target_soc * 40.0
        if bat >= target_kwh - 1e-6:
            return
        if obs.announced:
            for task in obs.announced:
                if actions.check_insertion(obs.vehicle_id, task.request_id).feasible:
                    return
        actions.request_return_depot(obs.vehicle_id, charge=True, target_soc=self.charge_target_soc)
