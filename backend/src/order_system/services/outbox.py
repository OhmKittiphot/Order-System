"""Reliable event publishing (transactional outbox on the order item).

Whenever an order needs an event published (creation, admin retry), the
same DynamoDB write that changes the order also sets::

    outboxStatus = "PENDING_PUBLISH", outboxEventType = <type>, outboxToken = <uuid>

The caller then publishes immediately and clears the marker. If the
Lambda crashes or SNS fails in between, the marker stays and the scheduled
outbox publisher (``handlers/outbox_publisher.py``) republishes it.
Consumers are idempotent, so publishing twice is safe; never publishing is
what this prevents.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..models.events import OrderEvent
from ..repositories.orders import OUTBOX_PENDING
from ..utils.common import iso_seconds_ago, retry_with_backoff
from ..utils.errors import TransientError
from ..utils.logging import get_logger
from .container import Deps

log = get_logger("outbox")


def outbox_fields(event_type: str) -> dict[str, Any]:
    return {"outboxStatus": OUTBOX_PENDING, "outboxEventType": event_type, "outboxToken": uuid.uuid4().hex}


def publish_event(deps: Deps, event_type: str, order: dict[str, Any], correlation_id: str | None) -> str:
    event = OrderEvent.create(event_type, order, correlation_id or order.get("correlationId"))
    message_id = retry_with_backoff(
        lambda: deps.publisher.publish(event), attempts=3, base_delay=0.05, retry_on=(TransientError,)
    )
    log.info(
        "event published",
        eventType=event_type,
        eventId=event.eventId,
        orderId=order["orderId"],
        attempt=event.attempt,
        messageId=message_id,
    )
    return message_id


def publish_from_outbox(deps: Deps, order: dict[str, Any], correlation_id: str | None = None) -> bool:
    """Publish the order's pending outbox event and clear the marker.
    Returns False (and leaves the marker) if publishing failed."""
    event_type = order.get("outboxEventType")
    token = order.get("outboxToken")
    if order.get("outboxStatus") != OUTBOX_PENDING or not event_type or not token:
        return True
    try:
        publish_event(deps, event_type, order, correlation_id)
    except TransientError as exc:
        log.warning("publish failed; outbox publisher will retry", orderId=order["orderId"], error=exc.message)
        return False
    deps.orders.clear_outbox(order["orderId"], token)
    return True


def sweep(deps: Deps) -> dict[str, int]:
    """Called on a schedule: republish events whose marker is older than the
    grace period (so we do not race the request that is publishing now)."""
    cutoff = iso_seconds_ago(deps.settings.outbox_min_age_seconds)
    pending = deps.orders.list_outbox(cutoff)
    published = failed = 0
    for order in pending:
        if publish_from_outbox(deps, order):
            published += 1
        else:
            failed += 1
    if pending:
        log.info("outbox sweep finished", found=len(pending), published=published, failed=failed)
    return {"found": len(pending), "published": published, "failed": failed}
