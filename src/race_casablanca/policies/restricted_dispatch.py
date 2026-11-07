"""Shared restricted-information dispatch rule (same logic for all comm modes)."""

from __future__ import annotations

from race_casablanca.sim.policy_api import ActionInterface, RestrictedObservation


def intended_claim_id(obs: RestrictedObservation, actions: ActionInterface) -> str | None:
    """Non-mutating intended claim under the shared restricted rule."""

    self_load = len(obs.own_committed)
    for task in sorted(obs.announced, key=lambda t: t.tw_end_s):
        defer = False
        for peer in obs.peers.values():
            if len(peer.committed) < self_load and self_load > 0:
                defer = True
                break
        if defer:
            continue
        chk = actions.check_insertion(obs.vehicle_id, task.request_id)
        if not chk.feasible:
            continue
        return task.request_id
    return None


def restricted_claim_pass(obs: RestrictedObservation, actions: ActionInterface) -> int:
    """One greedy claim pass using only legal restricted information.

    Returns number of successful claims this call.
    """

    n = 0
    self_load = len(obs.own_committed)
    for task in sorted(obs.announced, key=lambda t: t.tw_end_s):
        # Soft defer if a *messaged* peer reports fewer commitments
        defer = False
        for peer in obs.peers.values():
            if len(peer.committed) < self_load and self_load > 0:
                defer = True
                break
        if defer:
            continue
        chk = actions.check_insertion(obs.vehicle_id, task.request_id)
        if not chk.feasible:
            if task.tw_end_s <= obs.now_s:
                actions.reject_request(task.request_id)
            continue
        if actions.claim_task(obs.vehicle_id, task.request_id):
            n += 1
            break
    return n
