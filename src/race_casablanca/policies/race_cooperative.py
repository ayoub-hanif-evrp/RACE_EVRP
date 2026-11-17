"""RACE-COMM non-learning cooperative policy: energy-certified task bids + selective messaging.

Soft ranking is travel-primary (energy/slack tie-breakers). Hard feasibility is separate.
Restricted mode must not read live peer truth via ActionInterface.get_simulator().
"""

from __future__ import annotations

import random
from dataclasses import replace

from race_casablanca.coordination.race_csc import csc_should_claim
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
    peer_bid_trustworthy,
    resolve_peer_trust_mode,
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
        peer_trust_mode: str | None = None,
        ignore_peer_bids: bool = False,
        force_peer_wait_schedule: bool = False,
        claim_mode: str = "legacy",
        send_claim_signals: bool = True,
        wait_authority: str = "decentralized_signal",
        strip_peer_energy_fields: bool = False,
    ):
        """comm_mode includes none|periodic|full|random|selective|event_triggered|matched*.

        assign_wait_mode: ``legacy`` (1.25×delay) | ``deadline_energy`` (commit-now under tight slack).
        peer_trust_mode: ``ttl`` | ``ttl_commitment`` | ``delay_half`` (broken H_CURRENT) | ``none``.
        delay_aware_trust: legacy alias → delay_half when peer_trust_mode unset.
        ignore_peer_bids: claims ignore peers (H_NO_PEER) while messaging may still run.
        force_peer_wait_schedule: apply deadline wait even for none (NONE_MATCHED_WAIT).
        fair_physical_decisions: message/periodic update info only — no extra claims/charges.
        claim_mode: ``legacy`` (offer-rank deferral) | ``csc`` (commitment-safe).
        send_claim_signals: CSC broadcasts claim_intent/owned (ablation when False).
        wait_authority: ``decentralized_signal`` (TW+delay+local table; default) |
            ``coordinator_assisted`` (may probe all EV insertions — documented env authority).
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
        if assign_wait_mode not in {"legacy", "deadline_energy", "immediate"}:
            raise ValueError(f"unknown assign_wait_mode={assign_wait_mode}")
        if claim_mode not in {"legacy", "csc"}:
            raise ValueError(f"unknown claim_mode={claim_mode}")
        if wait_authority not in {"decentralized_signal", "coordinator_assisted"}:
            raise ValueError(f"unknown wait_authority={wait_authority}")
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
        self.peer_trust_mode = peer_trust_mode
        self.ignore_peer_bids = bool(ignore_peer_bids)
        self.force_peer_wait_schedule = bool(force_peer_wait_schedule)
        self.claim_mode = str(claim_mode)
        self.send_claim_signals = bool(send_claim_signals)
        self.wait_authority = str(wait_authority)
        self.strip_peer_energy_fields = bool(strip_peer_energy_fields)
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
        self.n_peer_bids_trusted = 0
        self.n_peer_bids_untrusted = 0
        self.n_wait_used_local_travel = 0
        self.n_claim_intents_sent = 0
        self.n_owned_announcements = 0
        self.n_csc_defers_to_credible = 0
        self.n_csc_safe_fallbacks = 0
        self.n_speculative_offers_ignored = 0
        self._sent: dict[tuple[str, str], BidMemory] = {}
        self._seq = 0
        # Own commitment versions only (never share across EVs via shared policy state).
        self._own_commit_version: dict[str, int] = {}
        # viewer_id -> sender_id -> max commitment_version observed in delivered messages.
        self._peer_commit_known: dict[str, dict[str, int]] = {}

    def expects_delayed_peer_bids(self) -> bool:
        """True only if this mode can deliver peer bids during an assign wait.

        ``none`` has no peers. ``periodic`` transmits only on timer ticks, not on
        bid_exchange — waiting ``message_delay`` does not gather peer bids.
        ``force_peer_wait_schedule`` overrides for NONE_MATCHED_WAIT ablation.
        """

        if self.force_peer_wait_schedule:
            return True
        return self.comm_mode not in {"none", "periodic"}

    def _coordinator_insertion_for_wait(self, sim, request_id: str) -> tuple[bool, float | None]:
        """Coordinator-assisted: probe each EV insertion (documented env authority only)."""

        best_travel: float | None = None
        any_feasible = False
        for vid in sim.vehicles:
            chk = sim.check_insertion(vid, request_id)
            if not chk.feasible:
                continue
            any_feasible = True
            travel = float(chk.marginal_travel_s)
            if best_travel is None or travel < best_travel:
                best_travel = travel
        return any_feasible, best_travel

    def _local_fresh_peer_count(self, sim, request_id: str, viewer_id: str) -> int:
        """Count peer senders known to one vehicle's local bid table only."""

        by_req = (getattr(sim, "local_bids", {}) or {}).get(viewer_id) or {}
        senders = by_req.get(request_id) or {}
        return sum(1 for s in senders if s != viewer_id)

    def assignment_wait_for_request(self, sim, request_id: str) -> float:
        """Env-scheduled assign window. Default wait uses decentralized signals only.

        ``decentralized_signal``: TW slack, message delay, roster size, and one viewer's
        local_bids coverage — no cross-fleet insertion probes.
        ``coordinator_assisted``: may probe all EV insertions (explicit authority).
        """

        req = sim.requests.get(request_id)
        if req is None:
            return 0.0
        task = TaskAnnouncement(
            req.request_id, req.snap_node, req.tw_start_s, req.tw_end_s, req.service_s, req.weight_kg
        )
        delay = float(sim.config.message_delay_s)
        self.message_delay_s = delay
        if self.assign_wait_mode == "immediate":
            self.n_assign_waits += 1
            return 0.0
        # CRITICAL: do not wait for nonexistent / non-arriving peer messages.
        if not self.expects_delayed_peer_bids() or delay <= 1e-12:
            self.n_assign_waits += 1
            return 0.0
        if self.assign_wait_mode == "deadline_energy":
            n_comp = max(0, len(sim.vehicles) - 1)
            viewer = next(iter(sim.vehicles))
            n_fresh = self._local_fresh_peer_count(sim, request_id, viewer)
            if self.wait_authority == "coordinator_assisted":
                local_feasible, local_travel = self._coordinator_insertion_for_wait(sim, request_id)
                if local_travel is not None:
                    self.n_wait_used_local_travel += 1
            else:
                # Decentralized: do not inspect peer physics. Assume open roster
                # competition; travel-based commit-now uses only TW/delay rules.
                local_feasible = True
                local_travel = None
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

        cv = self._own_commit_version.get(obs.vehicle_id, 0)
        tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)
        own_bids: dict[str, TaskBid] = {}
        for task in tasks:
            self._seq += 1
            own_bids[task.request_id] = compute_self_bid(
                obs, actions, task, ttl_s=self.bid_ttl_s, seq=self._seq, commitment_version=cv
            )
            # Learn peer commitment versions only from delivered messages.
            peers_here = self._peer_bids_for(obs, task.request_id)
            self._ingest_peer_versions(obs.vehicle_id, peers_here)

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
            self._own_commit_version[obs.vehicle_id] = cv + 1
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
            if self.strip_peer_energy_fields:
                # Ablation E: keep travel/feasibility; zero energy message fields.
                bid = replace(
                    bid,
                    marginal_energy_kwh=0.0,
                    energy_flex_kwh=0.0,
                    charge_burden_s=0.0,
                )
            if bid.is_fresh(obs.now_s):
                out.append(bid)
        return out

    def _ingest_peer_versions(self, viewer_id: str, peers: list[TaskBid]) -> None:
        """Record commitment versions only from messages delivered to this viewer."""

        known = self._peer_commit_known.setdefault(viewer_id, {})
        for b in peers:
            prev = known.get(b.sender_id)
            cv = int(b.commitment_version)
            if prev is None or cv > int(prev):
                known[b.sender_id] = cv

    def _known_versions_for(self, obs: RestrictedObservation) -> dict[str, int]:
        """Versions available to this EV: own + peer versions from its inbox only."""

        known = {obs.vehicle_id: int(self._own_commit_version.get(obs.vehicle_id, 0))}
        known.update(self._peer_commit_known.get(obs.vehicle_id, {}))
        return known

    def _claim_kwargs(self, obs: RestrictedObservation) -> dict:
        return dict(
            message_delay_s=float(self.message_delay_s),
            delay_aware_trust=self.delay_aware_trust,
            peer_trust_mode=self.peer_trust_mode,
            ignore_peer_bids=self.ignore_peer_bids,
            known_commitment_versions=self._known_versions_for(obs),
        )

    def _should_claim(
        self,
        own: TaskBid,
        peers: list[TaskBid],
        *,
        obs: RestrictedObservation,
    ) -> bool:
        kw = self._claim_kwargs(obs)
        if self.claim_mode == "csc":
            return csc_should_claim(own, peers, now_s=float(obs.now_s), **kw)
        return self_should_claim(own, peers, now_s=obs.now_s, **kw)

    def _tally_peer_trust(self, peers: list[TaskBid], *, now_s: float, obs: RestrictedObservation) -> None:
        mode = resolve_peer_trust_mode(
            peer_trust_mode=self.peer_trust_mode, delay_aware_trust=self.delay_aware_trust
        )
        known = self._known_versions_for(obs)
        for b in peers:
            ok = peer_bid_trustworthy(
                b,
                now_s=now_s,
                message_delay_s=float(self.message_delay_s),
                peer_trust_mode=mode,
                known_commitment_versions=known,
            )
            if ok:
                self.n_peer_bids_trusted += 1
            else:
                self.n_peer_bids_untrusted += 1
            # Speculative offer under delay: feasible offer without intent/owned.
            if (
                self.claim_mode == "csc"
                and float(self.message_delay_s) > 1e-12
                and ok
                and not bool(getattr(b, "claim_intent", False))
                and not bool(getattr(b, "owned", False))
            ):
                self.n_speculative_offers_ignored += 1

    def _intended_claim(self, obs: RestrictedObservation, own_bids: dict[str, TaskBid]) -> str | None:
        for task in sorted(obs.announced, key=lambda t: t.tw_end_s):
            own = own_bids.get(task.request_id)
            if own is None or not own.feasible:
                continue
            peers = self._peer_bids_for(obs, task.request_id)
            if self._should_claim(own, peers, obs=obs):
                return task.request_id
        return None

    def _broadcast_claim_signal(
        self,
        obs: RestrictedObservation,
        actions: ActionInterface,
        own: TaskBid,
        *,
        claim_intent: bool = False,
        owned: bool = False,
    ) -> None:
        if self.comm_mode == "none" or not self.send_claim_signals:
            return
        payload = own.to_payload()
        payload["claim_intent"] = bool(claim_intent)
        payload["owned"] = bool(owned)
        if owned:
            payload["feasible"] = True
            payload["withdrawn"] = False
        nbytes = actions.broadcast_task_bid(obs.vehicle_id, payload)
        self.n_messages_sent_by_policy += 1
        self.n_bid_bytes_sent += int(nbytes)
        if claim_intent:
            self.n_claim_intents_sent += 1
        if owned:
            self.n_owned_announcements += 1

    @staticmethod
    def _serialized_payload_bytes(payload: dict) -> int:
        import json

        return len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

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
                # Task-bid periodic: initial announcement when first eligible, then
                # 300s-timer refreshes for still-open feasible tasks (SimConfig.periodic_broadcast_s).
                if reason == "periodic_broadcast" and bool(own.feasible):
                    send = True
                    kind = "periodic"
                elif mem is None and bool(own.feasible) and reason in {
                    "bid_exchange",
                    "request_release",
                    "vehicle_idle",
                    "charge_end",
                    "service_end",
                    "epoch",
                }:
                    send = True
                    kind = "periodic_initial"
                else:
                    send = False
                    kind = "none"
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
                kind = "random_matched_bytes"
                send = False  # decided after measuring actual payload size
            elif self.comm_mode == "selective":
                send, kind = selective_should_send(own, peers, mem, now_s=obs.now_s)
            elif self.comm_mode == "event_triggered":
                send, kind = event_triggered_should_send(own, peers, mem, now_s=obs.now_s)

            payload = own.to_payload()
            if kind == "withdraw":
                payload["feasible"] = False
                payload["withdrawn"] = True
            if self.comm_mode == "random_matched_bytes":
                if self._matched_bytes is None:
                    continue
                nbytes_est = self._serialized_payload_bytes(payload)
                if not self._matched_bytes.allow(
                    self.rng, len(candidates), payload_bytes=float(nbytes_est)
                ):
                    continue
                send = True
            if not send:
                continue
            if kind == "withdraw":
                self.n_withdrawals += 1
            nbytes = actions.broadcast_task_bid(obs.vehicle_id, payload)
            self.n_messages_sent_by_policy += 1
            self.n_bid_bytes_sent += int(nbytes)
            self._sent[key] = BidMemory(bid=own, send_s=obs.now_s)

    def _send_commitment_invalidations(
        self, obs: RestrictedObservation, actions: ActionInterface, claimed_rid: str
    ) -> None:
        """After accepting a task, publish material updates for remaining announced tasks."""

        cv = self._own_commit_version.get(obs.vehicle_id, 0)
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
            payload = bid.to_payload()
            if self.comm_mode == "random_matched_bytes" and self._matched_bytes is not None:
                nbytes_est = self._serialized_payload_bytes(payload)
                if not self._matched_bytes.allow(
                    self.rng, n_candidates=1, payload_bytes=float(nbytes_est)
                ):
                    continue
            # Only refresh if we previously advertised interest
            nbytes = actions.broadcast_task_bid(obs.vehicle_id, payload)
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
            self._ingest_peer_versions(obs.vehicle_id, peers)
            self._tally_peer_trust(peers, now_s=float(obs.now_s), obs=obs)
            legacy_would = self_should_claim(
                own, peers, now_s=obs.now_s, **self._claim_kwargs(obs)
            )
            trusted = self._should_claim(own, peers, obs=obs)
            if self.claim_mode == "csc" and trusted and not legacy_would:
                self.n_csc_safe_fallbacks += 1
            mode = resolve_peer_trust_mode(
                peer_trust_mode=self.peer_trust_mode, delay_aware_trust=self.delay_aware_trust
            )
            if mode == "delay_half" and trusted:
                naive = self_should_claim(
                    own,
                    peers,
                    now_s=obs.now_s,
                    peer_trust_mode="ttl",
                    ignore_peer_bids=False,
                )
                if trusted and not naive:
                    self.n_claims_ignored_stale_peer += 1
            if not trusted:
                self.n_defers_to_peer += 1
                if self.claim_mode == "csc":
                    self.n_csc_defers_to_credible += 1
                continue
            # CSC: announce claim intent before registry attempt (nonbinding).
            if self.claim_mode == "csc" and self.send_claim_signals and self.comm_mode != "none":
                self._broadcast_claim_signal(obs, actions, own, claim_intent=True, owned=False)
            self.n_claims_attempted += 1
            # Fresh safety check at commitment time (bid never bypasses physics).
            chk = actions.check_insertion(obs.vehicle_id, task.request_id)
            if not chk.feasible:
                continue
            if actions.claim_task(obs.vehicle_id, task.request_id):
                self.n_claims_success += 1
                if self.claim_mode == "csc" and self.send_claim_signals and self.comm_mode != "none":
                    self._broadcast_claim_signal(obs, actions, own, claim_intent=False, owned=True)
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
