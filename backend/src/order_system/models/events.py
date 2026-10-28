"""Order lifecycle event schema (version 1.0).

Events are published to the ``order-events`` SNS topic with an
``eventType`` message attribute; SQS subscriptions filter on it and use raw
message delivery, so an SQS message body is exactly ``OrderEvent.to_json()``.

Events intentionally carry only identifiers. Consumers read the current
order from DynamoDB, which keeps PII and prices out of queues and makes
consumers robust to reordering.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ..utils.common import new_id, now_iso
from ..utils.errors import PermanentError

SCHEMA_VERSION = "1.0"


class EventType:
    ORDER_PLACED = "OrderPlaced"
    INVENTORY_RESERVED = "InventoryReserved"
    ORDER_CONFIRMED = "OrderConfirmed"
    ORDER_FAILED = "OrderFailed"

    ALL = (ORDER_PLACED, INVENTORY_RESERVED, ORDER_CONFIRMED, ORDER_FAILED)


@dataclass(frozen=True)
class OrderEvent:
    eventId: str
    eventType: str
    schemaVersion: str
    occurredAt: str
    orderId: str
    customerId: str
    attempt: int
    correlationId: str | None = None

    @classmethod
    def create(cls, event_type: str, order: dict[str, Any], correlation_id: str | None = None) -> OrderEvent:
        return cls(
            eventId=new_id("evt"),
            eventType=event_type,
            schemaVersion=SCHEMA_VERSION,
            occurredAt=now_iso(),
            orderId=order["orderId"],
            customerId=order["customerId"],
            attempt=int(order.get("attempt", 0)),
            correlationId=correlation_id,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def parse(cls, body: str) -> OrderEvent:
        """Parse an SQS body. Accepts raw delivery and SNS-envelope delivery."""
        try:
            data = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PermanentError("Message body is not valid JSON") from exc
        if isinstance(data, dict) and data.get("Type") == "Notification" and "Message" in data:
            try:
                data = json.loads(data["Message"])
            except json.JSONDecodeError as exc:
                raise PermanentError("SNS envelope message is not valid JSON") from exc
        if not isinstance(data, dict):
            raise PermanentError("Event must be a JSON object")
        missing = [f for f in ("eventId", "eventType", "orderId", "customerId") if not data.get(f)]
        if missing:
            raise PermanentError(f"Event is missing fields: {', '.join(missing)}")
        if data["eventType"] not in EventType.ALL:
            raise PermanentError(f"Unknown event type {data['eventType']}")
        if str(data.get("schemaVersion", "1.0")).split(".")[0] != SCHEMA_VERSION.split(".")[0]:
            raise PermanentError(f"Unsupported schema version {data.get('schemaVersion')}")
        attempt = data.get("attempt", 0)
        if not isinstance(attempt, int) or attempt < 0:
            raise PermanentError("attempt must be a non-negative integer")
        return cls(
            eventId=str(data["eventId"]),
            eventType=str(data["eventType"]),
            schemaVersion=str(data.get("schemaVersion", SCHEMA_VERSION)),
            occurredAt=str(data.get("occurredAt", "")),
            orderId=str(data["orderId"]),
            customerId=str(data["customerId"]),
            attempt=attempt,
            correlationId=data.get("correlationId"),
        )
