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
    MatchedByteBudgetController,
    event_triggered_should_send,
    selective_should_send,
)
from race_casablanca.coordination.task_bids import (
    TaskBid,
    assignment_wait_s,
    compute_self_bid,
    deadline_energy_assignment_wait_s,
    self_should_claim,
)
from race_casablanca.sim.policy_api import (
    ActionInterface,
    FullInfoObservation,
    RestrictedObservation,
    TaskAnnouncement,
)


# Physical claim / charge opportunities shared across treatments for fair causality.
# Message delivery and periodic ticks may update information / transmit bids only.
PHYSICAL_DECISION_REASONS = frozenset(
    {
        "bid_assign",
        "vehicle_idle",
        "charge_end",
        "service_end",
        "pickup_missed",
        "epoch",
    }
)
INFO_ONLY_REASONS = frozenset({"message", "periodic_broadcast", "bid_exchange"})


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
        matched_byte_budget: float | None = None,
        matched_n_recipients: int = 2,
        typical_payload_bytes: float = 400.0,
        rng_seed: int = 0,
        charge_target_soc: float = 0.70,
        enable_readiness_charge: bool = True,
        max_assign_wait_s: float = 120.0,
        urgency_slack_s: float = 180.0,
        assign_wait_mode: str = "legacy",
        delay_aware_trust: bool = False,
        message_delay_s: float = 0.0,
        fair_physical_decisions: bool = True,
    ):
        """comm_mode includes none|periodic|full|random|selective|event_triggered|matched*.

        assign_wait_mode: ``legacy`` (1.25×delay) | ``deadline_energy`` (commit-now under tight slack).
        delay_aware_trust: ignore stale peer bids when deferring under link delay.
        fair_physical_decisions: message/periodic update info only — no extra claims/charges.
        """

        allowed = {
            "none",
            "periodic",
            "full",
            "random",
            "selective",
            "event_triggered",
            "random_matched",
            "random_matched_bytes",
        }
        if comm_mode not in allowed:
            raise ValueError(f"unknown comm_mode={comm_mode}")
        if assign_wait_mode not in {"legacy", "deadline_energy"}:
            raise ValueError(f"unknown assign_wait_mode={assign_wait_mode}")
        self.comm_mode = comm_mode
        self.bid_ttl_s = float(bid_ttl_s)
        self.random_p_send = float(random_p_send)
        self.rng = random.Random(int(rng_seed))
        self.charge_target_soc = float(charge_target_soc)
        self.enable_readiness_charge = bool(enable_readiness_charge)
        self.max_assign_wait_s = float(max_assign_wait_s)
        self.urgency_slack_s = float(urgency_slack_s)
        self.assign_wait_mode = str(assign_wait_mode)
        self.delay_aware_trust = bool(delay_aware_trust)
        self.message_delay_s = float(message_delay_s)
        self.fair_physical_decisions = bool(fair_physical_decisions)
        self._matched = (
            MatchedBudgetController(
                budget=int(matched_message_budget),
                n_recipients=max(1, int(matched_n_recipients)),
            )
            if matched_message_budget is not None
            else None
        )
        self._matched_bytes = (
            MatchedByteBudgetController(
                budget_bytes=float(matched_byte_budget),
                typical_payload_bytes=float(typical_payload_bytes),
                n_recipients=max(1, int(matched_n_recipients)),
            )
            if matched_byte_budget is not None
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
        self.n_assign_waits = 0
        self.sum_assign_wait_s = 0.0
        self.n_claims_ignored_stale_peer = 0
        self.n_info_only_decisions = 0
        self.n_physical_claim_decisions = 0
        self._sent: dict[tuple[str, str], BidMemory] = {}
        self._seq = 0
        self._commit_version: dict[str, int] = {}

    def expects_delayed_peer_bids(self) -> bool:
        """True only if this mode can deliver peer bids during an assign wait.

        ``none`` has no peers. ``periodic`` transmits only on timer ticks, not on
        bid_exchange — waiting ``message_delay`` does not gather peer bids.
        """

        return self.comm_mode not in {"none", "periodic"}

    def assignment_wait_for_request(self, sim, request_id: str) -> float:
        req = sim.requests.get(request_id)
        if req is None:
            return 0.0
        task = TaskAnnouncement(
            req.request_id, req.snap_node, req.tw_start_s, req.tw_end_s, req.service_s, req.weight_kg
        )
        delay = float(sim.config.message_delay_s)
        self.message_delay_s = delay
        # CRITICAL: do not wait for nonexistent / non-arriving peer messages.
        if not self.expects_delayed_peer_bids() or delay <= 1e-12:
            self.n_assign_waits += 1
            return 0.0
        if self.assign_wait_mode == "deadline_energy":
            local_feasible = True
            local_travel = None
            n_comp = max(0, len(sim.vehicles) - 1)
            n_fresh = 0
            for _vid, by_req in (getattr(sim, "local_bids", {}) or {}).items():
                n_fresh += len(by_req.get(request_id) or {})
            wait = deadline_energy_assignment_wait_s(
                task,
                now_s=sim.now_s,
                message_delay_s=delay,
                max_wait_s=min(self.max_assign_wait_s, 60.0),
                urgency_slack_s=self.urgency_slack_s,
                local_feasible=local_feasible,
                local_travel_s=local_travel,
                n_roster_competitors=n_comp,
                n_fresh_peer_bids=n_fresh,
            )
        else:
            wait = assignment_wait_s(
                task,
                now_s=sim.now_s,
                message_delay_s=delay,
                max_wait_s=self.max_assign_wait_s,
                urgency_slack_s=self.urgency_slack_s,
            )
        self.n_assign_waits += 1
        self.sum_assign_wait_s += float(wait)
        return float(wait)

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

        info_only = bool(self.fair_physical_decisions) and reason in INFO_ONLY_REASONS
        if info_only:
            self.n_info_only_decisions += 1

        # Charging is a physical decision — only on the shared physical opportunity set.
        if self.enable_readiness_charge and (
            (not self.fair_physical_decisions and reason in (
                "request_release", "bid_exchange", "bid_assign", "charge_end", "epoch", "periodic_broadcast",
            ))
            or (self.fair_physical_decisions and reason in PHYSICAL_DECISION_REASONS)
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
        # Delayed full-comm cascade guard: message deliveries update local bid tables;
        # rebroadcasting on every delivery recreates the event flood. Communicate on
        # release / exchange / assign / periodic / charge / idle triggers instead.
        skip_comm = assign_only or (
            reason == "message"
            and self.comm_mode in {"full", "random", "random_matched", "random_matched_bytes", "event_triggered"}
        )

        if self.comm_mode != "none" and not skip_comm:
            self._maybe_communicate(obs, actions, own_bids, reason)

        if exchange_only or info_only:
            # Info-only: message/periodic may transmit or ingest bids, never claim/charge.
            if info_only and reason == "message" and obs.peer_bids:
                intended = self._intended_claim(obs, own_bids)
                intended_empty = self._intended_claim(replace(obs, peer_bids={}), own_bids)
                if intended != intended_empty:
                    self.n_counterfactual_decision_changes += 1
            return

        if obs.peer_bids and reason in ("bid_assign",):
            intended = self._intended_claim(obs, own_bids)
            intended_empty = self._intended_claim(replace(obs, peer_bids={}), own_bids)
            if intended != intended_empty:
                self.n_counterfactual_decision_changes += 1

        self.n_physical_claim_decisions += 1
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
            if self_should_claim(
                own,
                peers,
                now_s=obs.now_s,
                message_delay_s=float(self.message_delay_s),
                delay_aware_trust=self.delay_aware_trust,
            ):
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
            elif self.comm_mode == "random_matched_bytes":
                if self._matched_bytes is None:
                    send = False
                else:
                    send = self._matched_bytes.allow(self.rng, len(candidates))
                kind = "random_matched_bytes"
            elif self.comm_mode == "selective":
                send, kind = selective_should_send(own, peers, mem, now_s=obs.now_s)
            elif self.comm_mode == "event_triggered":
                send, kind = event_triggered_should_send(own, peers, mem, now_s=obs.now_s)

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
            # Matched-budget modes must charge invalidations or stop — otherwise
            # recipient totals systematically exceed the selective-calibrated budget.
            if self.comm_mode == "random_matched" and self._matched is not None:
                if not self._matched.allow(self.rng, n_candidates=1):
                    continue
            if self.comm_mode == "random_matched_bytes" and self._matched_bytes is not None:
                if not self._matched_bytes.allow(self.rng, n_candidates=1):
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
            delay = float(self.message_delay_s)
            trusted = self_should_claim(
                own,
                peers,
                now_s=obs.now_s,
                message_delay_s=delay,
                delay_aware_trust=self.delay_aware_trust,
            )
            if self.delay_aware_trust and trusted:
                naive = self_should_claim(own, peers, now_s=obs.now_s, delay_aware_trust=False)
                if trusted and not naive:
                    self.n_claims_ignored_stale_peer += 1
            if not trusted:
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
