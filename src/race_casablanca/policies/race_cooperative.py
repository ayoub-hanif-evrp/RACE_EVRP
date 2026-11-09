"""RACE-COMM non-learning cooperative policy: energy-certified task bids + selective messaging.

Same assignment rule under all communication modes; only messaging differs.
Restricted mode must not read live peer truth via ActionInterface.get_simulator().
"""

from __future__ import annotations

import random
from dataclasses import replace

from race_casablanca.coordination.selective_protocol import (
    BidMemory,
    random_should_send,
    selective_should_send,
)
from race_casablanca.coordination.task_bids import (
    TaskBid,
    compute_self_bid,
    self_should_claim,
)
from race_casablanca.sim.policy_api import (
    ActionInterface,
    FullInfoObservation,
    RestrictedObservation,
)


class RaceCooperativePolicy:
    name = "race_cooperative"
    # Enables simulator two-phase bid_exchange → bid_assign on request releases.
    two_phase_bidding = True

    def __init__(
        self,
        comm_mode: str = "selective",
        *,
        bid_ttl_s: float = 180.0,
        random_p_send: float = 0.25,
        rng_seed: int = 0,
        charge_target_soc: float = 0.70,
        enable_readiness_charge: bool = True,
    ):
        """comm_mode: none | periodic | full | random | selective."""

        allowed = {"none", "periodic", "full", "random", "selective"}
        if comm_mode not in allowed:
            raise ValueError(f"unknown comm_mode={comm_mode}")
        self.comm_mode = comm_mode
        self.bid_ttl_s = float(bid_ttl_s)
        self.random_p_send = float(random_p_send)
        self.rng = random.Random(int(rng_seed))
        self.charge_target_soc = float(charge_target_soc)
        self.enable_readiness_charge = bool(enable_readiness_charge)

        self.n_messages_sent_by_policy = 0
        self.n_bid_bytes_sent = 0
        self.n_claims_attempted = 0
        self.n_claims_success = 0
        self.n_defers_to_peer = 0
        self.n_message_driven_decision_invocations = 0
        self.n_counterfactual_decision_changes = 0
        self._sent: dict[tuple[str, str], BidMemory] = {}  # (vid, rid) -> memory

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if not isinstance(obs, RestrictedObservation):
            return
        # Hard guard: must not open the simulator escape hatch.
        try:
            actions.get_simulator()
            raise RuntimeError("restricted RaceCooperativePolicy obtained live simulator access")
        except PermissionError:
            pass

        if reason in ("message", "bid_assign"):
            self.n_message_driven_decision_invocations += 1

        # Optional readiness charging when idle and low SOC (local only).
        if self.enable_readiness_charge and reason in (
            "request_release",
            "bid_exchange",
            "bid_assign",
            "charge_end",
            "epoch",
            "periodic_broadcast",
        ):
            self._maybe_charge(obs, actions)

        tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)
        own_bids: dict[str, TaskBid] = {}
        for task in tasks:
            own_bids[task.request_id] = compute_self_bid(
                obs, actions, task, ttl_s=self.bid_ttl_s
            )

        exchange_only = reason == "bid_exchange"
        assign_only = reason == "bid_assign"

        # Communication step
        if self.comm_mode != "none" and not assign_only:
            self._maybe_communicate(obs, actions, own_bids, reason)

        if exchange_only:
            return

        # Counterfactual: would intended claim differ without peer bids?
        if obs.peer_bids and reason in ("message", "bid_assign", "periodic_broadcast"):
            intended = self._intended_claim(obs, own_bids)
            intended_empty = self._intended_claim(replace(obs, peer_bids={}), own_bids)
            if intended != intended_empty:
                self.n_counterfactual_decision_changes += 1

        self._claim_pass(obs, actions, own_bids)

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
            if self_should_claim(own, peers):
                return task.request_id
        return None

    def _maybe_communicate(
        self,
        obs: RestrictedObservation,
        actions: ActionInterface,
        own_bids: dict[str, TaskBid],
        reason: str,
    ) -> None:
        for rid, own in own_bids.items():
            peers = self._peer_bids_for(obs, rid)
            key = (obs.vehicle_id, rid)
            mem = self._sent.get(key)
            send = False
            if self.comm_mode == "full":
                send = True
            elif self.comm_mode == "periodic":
                # Only on periodic clock (and first release bursts use full for that event).
                send = reason == "periodic_broadcast"
            elif self.comm_mode == "random":
                send = random_should_send(self.rng, self.random_p_send)
            elif self.comm_mode == "selective":
                if reason == "message":
                    # Refresh only if selective trigger still fires
                    send = selective_should_send(own, peers, mem, now_s=obs.now_s)
                else:
                    send = selective_should_send(own, peers, mem, now_s=obs.now_s)

            if not send:
                continue
            nbytes = actions.broadcast_task_bid(obs.vehicle_id, own.to_payload())
            self.n_messages_sent_by_policy += 1
            self.n_bid_bytes_sent += int(nbytes)
            self._sent[key] = BidMemory(bid=own, send_s=obs.now_s)

    def _claim_pass(
        self,
        obs: RestrictedObservation,
        actions: ActionInterface,
        own_bids: dict[str, TaskBid],
    ) -> None:
        for task in sorted(obs.announced, key=lambda t: t.tw_end_s):
            own = own_bids[task.request_id]
            if not own.feasible:
                if task.tw_end_s <= obs.now_s:
                    actions.reject_request(task.request_id)
                continue
            peers = self._peer_bids_for(obs, task.request_id)
            if not self_should_claim(own, peers):
                self.n_defers_to_peer += 1
                continue
            self.n_claims_attempted += 1
            if actions.claim_task(obs.vehicle_id, task.request_id):
                self.n_claims_success += 1
                break

    def _maybe_charge(self, obs: RestrictedObservation, actions: ActionInterface) -> None:
        v = obs.self_state
        if v.busy or v.mode in ("SERVING", "CHARGING", "MOVING"):
            return
        # Approximate Bmax=40 kWh as in fleet_default; use relative fraction of current battery
        # Prefer return+charge when below target and no announced work or only infeasible work.
        bat = float(v.battery_kwh)
        # Without Bmax in obs, use absolute kWh threshold ~ 0.7*40
        target_kwh = self.charge_target_soc * 40.0
        if bat >= target_kwh - 1e-6:
            return
        if obs.announced:
            # Charge only if currently no feasible announced bid
            any_feas = False
            for task in obs.announced:
                chk = actions.check_insertion(obs.vehicle_id, task.request_id)
                if chk.feasible:
                    any_feas = True
                    break
            if any_feas:
                return
        actions.request_return_depot(obs.vehicle_id, charge=True, target_soc=self.charge_target_soc)
