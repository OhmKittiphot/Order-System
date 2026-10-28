"""SQS-triggered workers (one Lambda function each, same package).

* stock_handler   – stock-queue  (OrderPlaced)        → Stock Lambda
* payment_handler – payment-queue (InventoryReserved) → Payment Lambda
* notify_handler  – notify-queue (OrderConfirmed / OrderFailed) → Notify Lambda
* outbox_handler  – EventBridge schedule              → reliable publisher
"""

from __future__ import annotations

from typing import Any

from ..models.events import EventType, OrderEvent
from ..services import outbox
from ..services.container import get_deps
from ..services.workflow_service import WorkflowService
from ..utils.errors import PermanentError
from ..utils.logging import get_logger
from .sqs_batch import process_batch


def _expect(event: OrderEvent, *types: str) -> None:
    if event.eventType not in types:
        # A wrong event type means the SNS filter policy is misconfigured.
        raise PermanentError(f"Unexpected event type {event.eventType} for this queue")


def stock_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    def run(e: OrderEvent) -> str:
        _expect(e, EventType.ORDER_PLACED)
        return WorkflowService(get_deps()).handle_order_placed(e)

    return process_batch("stock-worker", "stock", event, run)


def payment_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    def run(e: OrderEvent) -> str:
        _expect(e, EventType.INVENTORY_RESERVED)
        return WorkflowService(get_deps()).handle_inventory_reserved(e)

    return process_batch("payment-worker", "payment", event, run)


def notify_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    def run(e: OrderEvent) -> str:
        _expect(e, EventType.ORDER_CONFIRMED, EventType.ORDER_FAILED)
        return WorkflowService(get_deps()).handle_order_outcome(e)

    return process_batch("notify-worker", "notify", event, run)


def outbox_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, int]:
    result = outbox.sweep(get_deps())
    get_logger("outbox-publisher").info("sweep complete", **result)
    return result
