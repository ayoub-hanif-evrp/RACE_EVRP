"""Configurable delayed messaging with stale-info semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Message:
    msg_id: int
    sender: str
    recipient: str  # vehicle_id or "dispatcher"
    kind: str
    payload: dict[str, Any]
    send_s: float
    deliver_s: float
    delivered: bool = False


@dataclass
class MessageBus:
    delay_s: float = 0.0
    cost_per_message: float = 1.0
    _seq: int = 0
    inbox: dict[str, list[Message]] = field(default_factory=dict)
    history: list[Message] = field(default_factory=list)
    n_sent: int = 0
    total_delay_s: float = 0.0
    total_cost: float = 0.0

    def send(
        self,
        sender: str,
        recipient: str,
        kind: str,
        payload: dict[str, Any],
        now_s: float,
        schedule_delivery: Callable[[float, Message], None] | None = None,
    ) -> Message:
        self._seq += 1
        deliver = now_s + max(0.0, self.delay_s)
        msg = Message(
            msg_id=self._seq,
            sender=sender,
            recipient=recipient,
            kind=kind,
            payload=dict(payload),
            send_s=now_s,
            deliver_s=deliver,
        )
        self.n_sent += 1
        self.total_delay_s += deliver - now_s
        self.total_cost += self.cost_per_message
        self.history.append(msg)
        if schedule_delivery is not None:
            schedule_delivery(deliver, msg)
        else:
            self.inbox.setdefault(recipient, []).append(msg)
        return msg

    def deliver(self, msg: Message) -> None:
        if msg.delivered:
            return
        msg.delivered = True
        self.inbox.setdefault(msg.recipient, []).append(msg)

    def pop_inbox(self, recipient: str) -> list[Message]:
        msgs = self.inbox.get(recipient, [])
        self.inbox[recipient] = []
        return msgs
