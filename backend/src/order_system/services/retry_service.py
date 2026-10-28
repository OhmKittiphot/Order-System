"""Admin recovery: failed-order retry, cancel, DLQ redrive.

Failure classification
----------------------
* BUSINESS (out of stock): retryable only after the cause is fixed — the
  service re-checks current stock and refuses otherwise.
* PAYMENT_DECLINED: not retryable; the customer must place a new order.
* Stuck / DLQ (TRANSIENT): order sat in PENDING or PROCESSING longer than
  ``STUCK_ORDER_SECONDS`` — usually because its message ended in a DLQ.
  Retry starts a new attempt and re-publishes the right event.
* Missing notification: re-publishes the outcome event (dedupe protects
  against double notification).
* PERMANENT (invalid messages): parked in the DLQ by the worker, never
  retried automatically; inspect and delete or fix them manually.

Every retry/cancel is an optimistic-locked update (``version`` must match
what was read) with a cooldown on ``lastRetryAt``; two admins clicking at the
same time cannot both succeed.
"""

from __future__ import annotations

from typing import Any

from ..models.events import EventType
from ..models.order_states import (
    FailureCategory,
    InventoryStatus,
    NotificationStatus,
    OrderStatus,
    PaymentStatus,
)
from ..repositories.orders import history_entry
from ..utils.common import iso_seconds_ago, now_iso, parse_iso, utc_now
from ..utils.errors import (
    ConditionFailedError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    TransactionCanceledError,
    TransientError,
)
from ..utils.logging import get_logger
from .container import Deps
from .outbox import outbox_fields, publish_from_outbox

log = get_logger("retry-service")

RESTART = "RESTART"  # new attempt from the stock step (after a business failure was fixed)
REPUBLISH_ORDER_PLACED = "REPUBLISH_ORDER_PLACED"  # stuck before/at the stock step
REPUBLISH_INVENTORY_RESERVED = "REPUBLISH_INVENTORY_RESERVED"  # stuck at the payment step
RENOTIFY = "RENOTIFY"  # outcome decided but customer not notified


class RetryService:
    def __init__(self, deps: Deps) -> None:
        self.deps = deps
        self.settings = deps.settings

    def _age_seconds(self, order: dict[str, Any]) -> float:
        return (utc_now() - parse_iso(order["updatedAt"])).total_seconds()

    def classify(self, order: dict[str, Any]) -> dict[str, Any]:
        status = order["status"]
        stuck = self._age_seconds(order) >= self.settings.stuck_order_seconds
        wait = f"Order is still being processed; retry becomes available after {self.settings.stuck_order_seconds}s without progress"

        def no(reason: str, category: str | None = None) -> dict[str, Any]:
            return {"retryable": False, "action": None, "reason": reason, "category": category}

        def yes(action: str, reason: str, category: str) -> dict[str, Any]:
            return {"retryable": True, "action": action, "reason": reason, "category": category}

        if int(order.get("attempt", 0)) >= self.settings.max_retries:
            return no(f"Retry limit of {self.settings.max_retries} reached")
        if status == OrderStatus.CANCELLED:
            return no("Order was cancelled")
        if status == OrderStatus.CONFIRMED:
            if order.get("notificationStatus") == NotificationStatus.PENDING and stuck:
                return yes(
                    RENOTIFY,
                    "Order confirmed but the customer notification did not complete",
                    FailureCategory.TRANSIENT,
                )
            return no("Order is already confirmed")
        if status == OrderStatus.FAILED:
            if order.get("inventoryStatus") == InventoryStatus.OUT_OF_STOCK:
                short = self._still_short(order)
                if short:
                    return no(
                        "Stock is still insufficient for: " + ", ".join(short) + ". Restock first.",
                        FailureCategory.BUSINESS,
                    )
                return yes(
                    RESTART, "Stock is now available; the order can be processed again", FailureCategory.BUSINESS
                )
            if order.get("paymentStatus") == PaymentStatus.FAILED:
                if order.get("notificationStatus") == NotificationStatus.PENDING and stuck:
                    return yes(
                        RENOTIFY,
                        "Payment declined and the customer notification did not complete",
                        FailureCategory.TRANSIENT,
                    )
                return no("Payment was declined; the customer must place a new order", FailureCategory.PAYMENT_DECLINED)
            return no("Failure is not retryable", FailureCategory.PERMANENT)
        if status == OrderStatus.PENDING:
            if stuck:
                return yes(
                    REPUBLISH_ORDER_PLACED,
                    "Stock step did not complete (message may be in the stock DLQ)",
                    FailureCategory.TRANSIENT,
                )
            return no(wait)
        if status == OrderStatus.PROCESSING and order.get("paymentStatus") == PaymentStatus.PENDING:
            if stuck:
                return yes(
                    REPUBLISH_INVENTORY_RESERVED,
                    "Payment step did not complete (message may be in the payment DLQ)",
                    FailureCategory.TRANSIENT,
                )
            return no(wait)
        return no("Order is not in a retryable state")

    def _still_short(self, order: dict[str, Any]) -> list[str]:
        stock = self.deps.catalog.get_inventories([i["productId"] for i in order["items"]])
        return [
            i["name"] or i["productId"]
            for i in order["items"]
            if int(stock.get(i["productId"], {}).get("available", 0)) < int(i["quantity"])
        ]

    def _load(self, order_id: str) -> dict[str, Any]:
        order = self.deps.orders.get(order_id)
        if not order:
            raise NotFoundError("Order not found")
        return order

    def retry(self, order_id: str, admin_id: str, correlation_id: str) -> dict[str, Any]:
        order = self._load(order_id)
        decision = self.classify(order)
        if not decision["retryable"]:
            raise ConflictError(decision["reason"], code="NOT_RETRYABLE", details=decision)
        action = decision["action"]
        now = now_iso()
        new_attempt = int(order.get("attempt", 0)) + (0 if action == RENOTIFY else 1)

        fields: dict[str, Any] = {"lastRetryAt": now, "lastRetryBy": admin_id, "attempt": new_attempt}
        remove: tuple[str, ...] = ()
        if action == RESTART:
            fields.update(
                status=OrderStatus.PENDING,
                inventoryStatus=InventoryStatus.PENDING,
                paymentStatus=PaymentStatus.PENDING,
                notificationStatus=NotificationStatus.PENDING,
            )
            remove = ("failureReason", "failureCategory")
            event_type = EventType.ORDER_PLACED
        elif action == REPUBLISH_ORDER_PLACED:
            event_type = EventType.ORDER_PLACED
        elif action == REPUBLISH_INVENTORY_RESERVED:
            event_type = EventType.INVENTORY_RESERVED
        else:
            event_type = (
                EventType.ORDER_CONFIRMED if order["status"] == OrderStatus.CONFIRMED else EventType.ORDER_FAILED
            )
        fields.update(outbox_fields(event_type))

        spec = self.deps.orders.transition_spec(
            expect={"version": order["version"], "status": order["status"]},
            set_fields=fields,
            remove=remove,
            history=history_entry("AdminRetry", f"{decision['reason']} (attempt {new_attempt})", fields.get("status")),
            extra_condition="attribute_not_exists(#lr) OR #lr <= :cutoff",
            extra_names={"#lr": "lastRetryAt"},
            extra_values={":cutoff": iso_seconds_ago(self.settings.retry_cooldown_seconds)},
        )
        try:
            updated = self.deps.orders.apply(order_id, spec)
        except ConditionFailedError as exc:
            raise ConflictError(
                "Order changed or was retried moments ago; refresh and try again", code="RETRY_CONFLICT"
            ) from exc
        published = publish_from_outbox(self.deps, updated, correlation_id)
        log.info("order retried", orderId=order_id, action=action, attempt=new_attempt, published=published)
        return {
            "orderId": order_id,
            "action": action,
            "attempt": new_attempt,
            "status": updated["status"],
            "eventPublished": published,
            "message": decision["reason"],
        }

    def cancel(self, order_id: str, admin_id: str) -> dict[str, Any]:
        order = self._load(order_id)
        status = order["status"]
        if status in (OrderStatus.CONFIRMED, OrderStatus.CANCELLED):
            raise ConflictError(f"A {status} order cannot be cancelled", code="NOT_CANCELLABLE")
        reserved = order.get("inventoryStatus") == InventoryStatus.RESERVED
        fields: dict[str, Any] = {"status": OrderStatus.CANCELLED, "cancelledBy": admin_id}
        if order.get("paymentStatus") == PaymentStatus.PENDING:
            fields["paymentStatus"] = PaymentStatus.SKIPPED
        if order.get("notificationStatus") == NotificationStatus.PENDING:
            fields["notificationStatus"] = NotificationStatus.SKIPPED
        if reserved:
            fields["inventoryStatus"] = InventoryStatus.RELEASED
        spec = self.deps.orders.transition_spec(
            expect={"version": order["version"], "status": status, "inventoryStatus": order["inventoryStatus"]},
            set_fields=fields,
            remove=("outboxStatus", "outboxEventType", "outboxToken"),
            history=history_entry(
                "Cancelled",
                "Cancelled by administrator" + ("; reserved stock released" if reserved else ""),
                OrderStatus.CANCELLED,
            ),
        )
        ops = [self.deps.orders.transition_op(order_id, spec)]
        if reserved:
            ops += [self.deps.catalog.release_op(i["productId"], int(i["quantity"])) for i in order["items"]]
        try:
            self.deps.gw.transact_write(ops)
        except TransactionCanceledError as exc:
            if exc.is_conflict:
                raise TransientError("Concurrent update, please retry") from exc
            raise ConflictError(
                "Order changed while cancelling; refresh and try again", code="CANCEL_CONFLICT"
            ) from exc
        log.info("order cancelled", orderId=order_id, released=reserved)
        return {"orderId": order_id, "status": OrderStatus.CANCELLED, "stockReleased": reserved}

    def redrive(self, queue: str) -> dict[str, Any]:
        cfg = self.settings.queues.get(queue)
        if not cfg or not cfg.dlq_arn or not cfg.queue_arn:
            raise NotFoundError(f"Queue {queue} is not configured")
        if self.deps.queues is None:
            raise ServiceUnavailableError("SQS is not available in this environment")
        try:
            handle = self.deps.queues.start_redrive(cfg.dlq_arn, cfg.queue_arn)
        except Exception as exc:  # noqa: BLE001 - e.g. a move task already running / not permitted in the lab
            log.warning("redrive failed", queue=queue, error=str(exc)[:300])
            raise ConflictError(
                "Could not start the DLQ redrive (a redrive may already be running, or the lab role lacks "
                "sqs:StartMessageMoveTask). Use the console 'Start DLQ redrive' button instead.",
                code="REDRIVE_FAILED",
            ) from exc
        log.info("dlq redrive started", queue=queue, taskHandle=handle)
        return {
            "queue": queue,
            "taskHandle": handle,
            "message": "Redrive started; messages move back to the source queue",
        }
