"""Asynchronous order processing: stock reservation, simulated payment and
customer notification. Each handler is idempotent.

Duplicate / late messages
-------------------------
SQS is at-least-once and SNS fan-out can reorder messages, so every handler:

1. Re-reads the order (events only carry ids).
2. Ignores events whose ``attempt`` is older than the order's current
   ``attempt`` (a retry has superseded them).
3. Performs its state change as a DynamoDB transaction whose order update is
   conditioned on the *expected source state*. A duplicate fails the
   condition and changes nothing.
4. After a failed condition it looks at the current state and, if this step
   already completed but the follow-up event may not have been published
   (e.g. the Lambda crashed after the commit), re-publishes the follow-up
   event. Downstream handlers are idempotent, so this is safe.
"""

from __future__ import annotations

import random
from typing import Any

from ..models.events import EventType, OrderEvent
from ..models.order_states import (
    FailureCategory,
    InventoryStatus,
    NotificationStatus,
    OrderStatus,
    PaymentStatus,
)
from ..repositories.orders import history_entry
from ..utils.common import new_id, now_iso
from ..utils.errors import (
    ConditionFailedError,
    PermanentError,
    TransactionCanceledError,
    TransientError,
)
from ..utils.logging import bind, get_logger
from .container import Deps
from .outbox import publish_event
from .views import money

log = get_logger("workflow")


class WorkflowService:
    def __init__(self, deps: Deps, rng: random.Random | None = None) -> None:
        self.deps = deps
        self.settings = deps.settings
        self.rng = rng or random.Random()  # noqa: S311 - simulation, not security

    # -- shared ---------------------------------------------------------------------
    def _load(self, event: OrderEvent) -> dict[str, Any] | None:
        """Returns the order, or None if the event is stale."""
        bind(orderId=event.orderId, eventType=event.eventType, eventId=event.eventId, attempt=event.attempt)
        order = self.deps.orders.get(event.orderId)
        if order is None:
            raise PermanentError(f"Order {event.orderId} does not exist")
        if order["customerId"] != event.customerId:
            raise PermanentError("Event customerId does not match the order")
        current = int(order.get("attempt", 0))
        if event.attempt < current:
            log.info("stale event ignored", orderAttempt=current)
            return None
        if event.attempt > current:
            raise PermanentError("Event attempt is newer than the order attempt")
        return order

    def _publish(self, event_type: str, order: dict[str, Any], event: OrderEvent) -> None:
        publish_event(self.deps, event_type, order, event.correlationId)

    # -- stock service ------------------------------------------------------------------
    def handle_order_placed(self, event: OrderEvent) -> str:
        order = self._load(event)
        if order is None:
            return "STALE"
        if order["status"] == OrderStatus.PENDING and order["inventoryStatus"] == InventoryStatus.PENDING:
            self.deps.orders.add_processing_attempt(order["orderId"])
            return self._reserve(order, event)
        return self._resume_after_stock(event)

    def _reserve(self, order: dict[str, Any], event: OrderEvent) -> str:
        items = order["items"]
        orders = self.deps.orders
        spec = orders.transition_spec(
            expect={
                "status": OrderStatus.PENDING,
                "inventoryStatus": InventoryStatus.PENDING,
                "attempt": event.attempt,
            },
            set_fields={"status": OrderStatus.PROCESSING, "inventoryStatus": InventoryStatus.RESERVED},
            history=history_entry(
                "InventoryReserved", "Stock reserved for all items; waiting for payment", OrderStatus.PROCESSING
            ),
        )
        ops = [self.deps.catalog.reserve_op(line["productId"], int(line["quantity"])) for line in items]
        ops.append(orders.transition_op(order["orderId"], spec))
        try:
            self.deps.gw.transact_write(ops)
        except TransactionCanceledError as exc:
            if exc.is_conflict:
                raise TransientError("Inventory transaction conflict") from exc
            failed = exc.failed_indexes()
            if len(items) in failed:  # the order condition failed -> duplicate / concurrent change
                return self._resume_after_stock(event)
            short = [items[i]["name"] or items[i]["productId"] for i in failed if i < len(items)]
            return self._mark_out_of_stock(order, event, short)
        log.info("inventory reserved", lines=len(items))
        updated = dict(order, status=OrderStatus.PROCESSING, inventoryStatus=InventoryStatus.RESERVED)
        self._publish(EventType.INVENTORY_RESERVED, updated, event)
        return "RESERVED"

    def _mark_out_of_stock(self, order: dict[str, Any], event: OrderEvent, products: list[str]) -> str:
        reason = "Insufficient stock for: " + ", ".join(products)
        spec = self.deps.orders.transition_spec(
            expect={
                "status": OrderStatus.PENDING,
                "inventoryStatus": InventoryStatus.PENDING,
                "attempt": event.attempt,
            },
            set_fields={
                "status": OrderStatus.FAILED,
                "inventoryStatus": InventoryStatus.OUT_OF_STOCK,
                "paymentStatus": PaymentStatus.SKIPPED,
                "failureCategory": FailureCategory.BUSINESS,
                "failureReason": reason,
            },
            history=history_entry("OutOfStock", reason, OrderStatus.FAILED),
        )
        try:
            updated = self.deps.orders.apply(order["orderId"], spec)
        except ConditionFailedError:
            return self._resume_after_stock(event)
        log.warning("order rejected: out of stock", products=products)
        self._publish(EventType.ORDER_FAILED, updated, event)
        return "OUT_OF_STOCK"

    def _resume_after_stock(self, event: OrderEvent) -> str:
        order = self.deps.orders.get(event.orderId) or {}
        if int(order.get("attempt", 0)) != event.attempt:
            return "STALE"
        if (
            order.get("status") == OrderStatus.PROCESSING
            and order.get("inventoryStatus") == InventoryStatus.RESERVED
            and order.get("paymentStatus") == PaymentStatus.PENDING
        ):
            log.info("duplicate OrderPlaced: re-publishing InventoryReserved")
            self._publish(EventType.INVENTORY_RESERVED, order, event)
            return "REPUBLISHED"
        if (
            order.get("status") == OrderStatus.FAILED
            and order.get("inventoryStatus") == InventoryStatus.OUT_OF_STOCK
            and order.get("notificationStatus") == NotificationStatus.PENDING
        ):
            self._publish(EventType.ORDER_FAILED, order, event)
            return "REPUBLISHED"
        log.info("duplicate OrderPlaced ignored", status=order.get("status"))
        return "DUPLICATE"

    # -- payment service -------------------------------------------------------------------
    def simulate_payment(self, order: dict[str, Any]) -> tuple[str, str | None]:
        """Simulated gateway. Deterministic test products (admin-configured,
        honoured only when ENABLE_TEST_SCENARIOS=true) drive failures:

        * PAYMENT_DECLINE         -> declined
        * PAYMENT_TRANSIENT_ONCE  -> transient error while attempt == 0, so the
          message ends in the DLQ and an admin retry (attempt 1) succeeds.
        """
        behaviors = (
            {line.get("testBehavior") for line in order.get("items", [])}
            if self.settings.enable_test_scenarios
            else set()
        )
        if "PAYMENT_TRANSIENT_ONCE" in behaviors and int(order.get("attempt", 0)) == 0:
            raise TransientError("Simulated payment provider timeout")
        if "PAYMENT_DECLINE" in behaviors:
            return PaymentStatus.FAILED, "Simulated card decline (test product)"
        if self.settings.is_payment_random and self.rng.random() < self.settings.payment_failure_rate:
            return PaymentStatus.FAILED, "Simulated random decline"
        return PaymentStatus.SUCCEEDED, None

    def handle_inventory_reserved(self, event: OrderEvent) -> str:
        order = self._load(event)
        if order is None:
            return "STALE"
        if not (
            order["status"] == OrderStatus.PROCESSING
            and order["inventoryStatus"] == InventoryStatus.RESERVED
            and order["paymentStatus"] == PaymentStatus.PENDING
        ):
            return self._resume_after_payment(event)
        self.deps.orders.add_processing_attempt(order["orderId"])
        outcome, reason = self.simulate_payment(order)  # may raise TransientError -> SQS retry -> DLQ
        succeeded = outcome == PaymentStatus.SUCCEEDED
        payment = {
            "orderId": order["orderId"],
            "attempt": event.attempt,
            "paymentId": new_id("pay"),
            "status": outcome,
            "amountMinor": int(order["totalMinor"]),
            "currency": order["currency"],
            "provider": "SIMULATED",
            "createdAt": now_iso(),
        }
        if reason:
            payment["reason"] = reason
        catalog = self.deps.catalog
        if succeeded:
            fields: dict[str, Any] = {
                "status": OrderStatus.CONFIRMED,
                "paymentStatus": PaymentStatus.SUCCEEDED,
                "inventoryStatus": InventoryStatus.COMMITTED,
            }
            hist = history_entry(
                "PaymentSucceeded", "Simulated payment approved; order confirmed", OrderStatus.CONFIRMED
            )
            stock_ops = [catalog.commit_op(i["productId"], int(i["quantity"])) for i in order["items"]]
        else:
            fields = {
                "status": OrderStatus.FAILED,
                "paymentStatus": PaymentStatus.FAILED,
                "inventoryStatus": InventoryStatus.RELEASED,
                "failureCategory": FailureCategory.PAYMENT_DECLINED,
                "failureReason": reason,
            }
            hist = history_entry("PaymentFailed", f"{reason}; reserved stock released", OrderStatus.FAILED)
            stock_ops = [catalog.release_op(i["productId"], int(i["quantity"])) for i in order["items"]]
        spec = self.deps.orders.transition_spec(
            expect={
                "status": OrderStatus.PROCESSING,
                "inventoryStatus": InventoryStatus.RESERVED,
                "paymentStatus": PaymentStatus.PENDING,
                "attempt": event.attempt,
            },
            set_fields=fields,
            history=hist,
        )
        ops = [self.deps.payments.put_op(payment), self.deps.orders.transition_op(order["orderId"], spec), *stock_ops]
        try:
            self.deps.gw.transact_write(ops)
        except TransactionCanceledError as exc:
            if exc.is_conflict:
                raise TransientError("Payment transaction conflict") from exc
            failed = exc.failed_indexes()
            if 0 in failed or 1 in failed:  # payment exists / order moved on -> duplicate
                return self._resume_after_payment(event)
            raise PermanentError("Inventory reservation is inconsistent with the order") from exc
        updated = dict(order, **fields)
        if succeeded:
            log.info("payment succeeded", amountMinor=payment["amountMinor"])
            self._publish(EventType.ORDER_CONFIRMED, updated, event)
            return "CONFIRMED"
        log.warning("payment declined; stock released", reason=reason)
        self._publish(EventType.ORDER_FAILED, updated, event)
        return "PAYMENT_FAILED"

    def _resume_after_payment(self, event: OrderEvent) -> str:
        order = self.deps.orders.get(event.orderId) or {}
        if int(order.get("attempt", 0)) != event.attempt:
            return "STALE"
        pending_notify = order.get("notificationStatus") == NotificationStatus.PENDING
        if order.get("status") == OrderStatus.CONFIRMED and pending_notify:
            self._publish(EventType.ORDER_CONFIRMED, order, event)
            return "REPUBLISHED"
        if (
            order.get("status") == OrderStatus.FAILED
            and order.get("paymentStatus") == PaymentStatus.FAILED
            and pending_notify
        ):
            self._publish(EventType.ORDER_FAILED, order, event)
            return "REPUBLISHED"
        log.info("duplicate/irrelevant InventoryReserved ignored", status=order.get("status"))
        return "DUPLICATE"

    # -- notification service ---------------------------------------------------------------
    def handle_order_outcome(self, event: OrderEvent) -> str:
        order = self._load(event)
        if order is None:
            return "STALE"
        expected = OrderStatus.CONFIRMED if event.eventType == EventType.ORDER_CONFIRMED else OrderStatus.FAILED
        if order["status"] != expected:
            log.info("notification skipped: order state changed", status=order["status"])
            return "STATE_CHANGED"

        amount = money(int(order["totalMinor"]), order["currency"])
        short_id = order["orderId"][-8:]
        if expected == OrderStatus.CONFIRMED:
            title = f"Order …{short_id} confirmed"
            message = f"Your order {order['orderId']} is confirmed. Total paid: {amount}."
        else:
            title = f"Order …{short_id} could not be completed"
            message = f"Your order {order['orderId']} failed: {order.get('failureReason', 'processing error')}."

        email_enabled = self.deps.email is not None
        notification_id = f"ntf_{order['orderId']}_{event.attempt}_{event.eventType}"
        record = {
            "notificationId": notification_id,
            "customerId": order["customerId"],
            "orderId": order["orderId"],
            "attempt": event.attempt,
            "type": event.eventType,
            "orderStatus": order["status"],
            "title": title,
            "message": message,
            "createdAt": now_iso(),
            "channels": ["IN_APP", "EMAIL"] if email_enabled else ["IN_APP"],
            "emailStatus": "PENDING" if email_enabled else "NOT_CONFIGURED",
            "emailAttempts": 0,
        }
        created = self.deps.notifications.create_if_absent(record)
        current = record if created else (self.deps.notifications.get(notification_id) or record)
        if not created:
            log.info("notification already recorded (dedupe)", notificationId=notification_id)

        if self.deps.email is not None and current.get("emailStatus") in ("PENDING", "FAILED"):
            try:
                message_id = self.deps.email.publish(order["customerId"], title, message)
            except TransientError:
                self.deps.notifications.mark_email(notification_id, "FAILED")
                raise
            # Accepted by SNS != delivered to the inbox.
            self.deps.notifications.mark_email(notification_id, "ACCEPTED_BY_SNS", message_id)

        spec = self.deps.orders.transition_spec(
            expect={"attempt": event.attempt, "status": expected, "notificationStatus": NotificationStatus.PENDING},
            set_fields={"notificationStatus": NotificationStatus.SENT},
            history=history_entry(
                "CustomerNotified",
                "In-app notification recorded" + (" and email handed to SNS" if email_enabled else ""),
            ),
        )
        try:
            self.deps.orders.apply(order["orderId"], spec)
        except ConditionFailedError:
            log.info("order notificationStatus already updated")
        return "NOTIFIED" if created else "DUPLICATE"
