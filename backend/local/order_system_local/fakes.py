"""In-memory stand-ins for SNS, SQS and CloudWatch.

Used by unit tests and the local dev server. ``InMemoryBus`` mimics the
production topology: one topic, three queues with SNS filter policies, raw
delivery, a DLQ per queue and ``maxReceiveCount = 3``.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from order_system.models.events import EventType, OrderEvent
from order_system.utils.errors import (
    TransientError,
)

SUBSCRIPTIONS: dict[str, tuple[str, ...]] = {
    "stock": (EventType.ORDER_PLACED,),
    "payment": (EventType.INVENTORY_RESERVED,),
    "notify": (EventType.ORDER_CONFIRMED, EventType.ORDER_FAILED),
}
MAX_RECEIVE_COUNT = 3


@dataclass
class Message:
    message_id: str
    body: str
    receive_count: int = 0
    attributes: dict[str, str] = field(default_factory=dict)


class InMemoryBus:
    """Topic + queues + DLQs. Thread-safe."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.queues: dict[str, list[Message]] = {name: [] for name in SUBSCRIPTIONS}
        self.dlqs: dict[str, list[Message]] = {name: [] for name in SUBSCRIPTIONS}
        self.published: list[OrderEvent] = []
        self.fail_next_publishes = 0

    # EventPublisher
    def publish(self, event: OrderEvent) -> str:
        with self.lock:
            if self.fail_next_publishes > 0:
                self.fail_next_publishes -= 1
                raise TransientError("Simulated SNS outage")
            self.published.append(event)
            for queue, types in SUBSCRIPTIONS.items():
                if event.eventType in types:  # SNS filter policy on eventType
                    self.queues[queue].append(Message(uuid.uuid4().hex, event.to_json()))
            return uuid.uuid4().hex

    def drain(self, handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]], max_rounds: int = 50) -> int:
        """Deliver messages to handlers until queues are empty (or only
        contain messages that keep failing and have been moved to DLQs)."""
        processed = 0
        for _ in range(max_rounds):
            delivered = False
            for queue, handler in handlers.items():
                with self.lock:
                    batch = self.queues[queue][:10]
                    self.queues[queue] = self.queues[queue][10:]
                if not batch:
                    continue
                delivered = True
                for m in batch:
                    m.receive_count += 1
                records = [
                    {
                        "messageId": m.message_id,
                        "body": m.body,
                        "attributes": {"ApproximateReceiveCount": str(m.receive_count)},
                        "eventSource": "aws:sqs",
                    }
                    for m in batch
                ]
                result = handler({"Records": records})
                failed = {f["itemIdentifier"] for f in result.get("batchItemFailures", [])}
                with self.lock:
                    for m in batch:
                        processed += 1
                        if m.message_id not in failed:
                            continue
                        if m.receive_count >= MAX_RECEIVE_COUNT:
                            self.dlqs[queue].append(m)  # SQS redrive policy
                        else:
                            self.queues[queue].append(m)
            if not delivered:
                break
        return processed

    def counts(self) -> dict[str, dict[str, int]]:
        with self.lock:
            return {q: {"queue": len(self.queues[q]), "dlq": len(self.dlqs[q])} for q in SUBSCRIPTIONS}


class FakeQueueAdmin:
    """SQS admin operations backed by the bus. Queue URLs are ``local://<name>``
    and ``local://<name>-dlq``."""

    def __init__(self, bus: InMemoryBus) -> None:
        self.bus = bus

    def _resolve(self, url: str) -> tuple[list[Message], str]:
        name = url.removeprefix("local://")
        if name.endswith("-dlq"):
            return self.bus.dlqs[name[:-4]], name
        return self.bus.queues[name], name

    def attributes(self, queue_url: str) -> dict[str, int]:
        messages, _ = self._resolve(queue_url)
        return {"ApproximateNumberOfMessages": len(messages), "ApproximateNumberOfMessagesNotVisible": 0}

    def start_redrive(self, source_arn: str, destination_arn: str) -> str:
        src, _ = self._resolve(source_arn)
        dst, _ = self._resolve(destination_arn)
        with self.bus.lock:
            for m in src:
                m.receive_count = 0
                dst.append(m)
            src.clear()
        return "local-task-" + uuid.uuid4().hex[:8]

    def send(self, queue_url: str, body: str, attributes: dict[str, str]) -> None:
        messages, _ = self._resolve(queue_url)
        with self.bus.lock:
            messages.append(Message(uuid.uuid4().hex, body, attributes=attributes))


class FakeEmailNotifier:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.subscriptions: list[dict[str, str]] = []
        self.fail_next = 0

    def publish(self, customer_id: str, subject: str, message: str) -> str:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise TransientError("Simulated SNS email outage")
        self.sent.append({"customerId": customer_id, "subject": subject, "message": message})
        return uuid.uuid4().hex

    def subscribe(self, email: str, customer_id: str) -> str:
        self.subscriptions.append({"email": email, "customerId": customer_id})
        return "pending confirmation"


class FakeAlarmReader:
    def __init__(self, bus: InMemoryBus) -> None:
        self.bus = bus

    def alarms(self, prefix: str) -> list[dict[str, Any]]:
        return [
            {
                "name": f"{prefix}{q}-dlq-not-empty",
                "state": "ALARM" if c["dlq"] else "OK",
                "reason": "local simulation",
                "updatedAt": "",
            }
            for q, c in self.bus.counts().items()
        ]
