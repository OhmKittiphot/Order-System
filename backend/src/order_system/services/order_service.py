"""Customer order use cases: place order, view order, order history,
notifications."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..models.events import EventType
from ..models.order_states import (
    InventoryStatus,
    NotificationStatus,
    OrderStatus,
    PaymentStatus,
)
from ..repositories.orders import history_entry
from ..utils.common import decode_token, encode_token, epoch_in, new_id, now_iso
from ..utils.errors import (
    ConflictError,
    NotFoundError,
    TransactionCanceledError,
    TransientError,
    ValidationError,
)
from ..utils.http import Principal
from ..utils.logging import bind, get_logger
from .container import Deps
from .outbox import outbox_fields, publish_from_outbox
from .views import notification_view, order_view

log = get_logger("order-service")


def _request_hash(lines: list[tuple[str, int]]) -> str:
    canonical = json.dumps(sorted(lines), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class OrderService:
    def __init__(self, deps: Deps) -> None:
        self.deps = deps
        self.settings = deps.settings

    # -- place order -------------------------------------------------------------
    def create_order(
        self, principal: Principal, idempotency_key: str, lines: list[tuple[str, int]], correlation_id: str
    ) -> tuple[int, dict[str, Any]]:
        customer_id = principal.user_id
        idem_id = f"{customer_id}#{idempotency_key}"
        request_hash = _request_hash(lines)

        replay = self._replay(idem_id, request_hash)
        if replay is not None:
            return replay

        products = self.deps.catalog.get_products([pid for pid, _ in lines])
        missing = [pid for pid, _ in lines if pid not in products or not products[pid].get("active")]
        if missing:
            raise ValidationError(
                "Some products do not exist or are not available",
                code="INVALID_PRODUCTS",
                details={"productIds": missing},
            )

        items: list[dict[str, Any]] = []
        total = 0
        for pid, qty in lines:
            product = products[pid]
            unit = int(product["priceMinor"])  # trusted server-side price
            line_total = unit * qty
            total += line_total
            line: dict[str, Any] = {
                "productId": pid,
                "name": product.get("name", ""),
                "unitPriceMinor": unit,
                "quantity": qty,
                "lineTotalMinor": line_total,
            }
            if self.settings.enable_test_scenarios and product.get("testBehavior"):
                line["testBehavior"] = product["testBehavior"]
            items.append(line)

        now = now_iso()
        order_id = new_id("ord")
        bind(orderId=order_id)
        order: dict[str, Any] = {
            "orderId": order_id,
            "entityType": "ORDER",
            "customerId": customer_id,
            "items": items,
            "itemCount": sum(q for _, q in lines),
            "totalMinor": total,
            "currency": self.settings.currency,
            "status": OrderStatus.PENDING,
            "inventoryStatus": InventoryStatus.PENDING,
            "paymentStatus": PaymentStatus.PENDING,
            "notificationStatus": NotificationStatus.PENDING,
            "attempt": 0,
            "version": 1,
            "processingAttempts": 0,
            "idempotencyKey": idempotency_key,
            "correlationId": correlation_id,
            "createdAt": now,
            "updatedAt": now,
            "history": [history_entry("OrderCreated", "Order received; waiting for stock check", OrderStatus.PENDING)],
            **outbox_fields(EventType.ORDER_PLACED),
        }
        idempotency = {
            "idempotencyId": idem_id,
            "orderId": order_id,
            "requestHash": request_hash,
            "createdAt": now,
            "expiresAt": epoch_in(self.settings.idempotency_ttl_hours),
        }
        try:
            self.deps.orders.create_with_idempotency(order, idempotency)
        except TransactionCanceledError as exc:
            if exc.is_conflict:
                raise TransientError("Concurrent request, please retry") from exc
            # Another request with the same key won the race.
            replay = self._replay(idem_id, request_hash)
            if replay is not None:
                return replay
            raise ConflictError("Order could not be created, please retry") from exc

        published = publish_from_outbox(self.deps, order, correlation_id)
        log.info("order created", totalMinor=total, lines=len(items), published=published)
        view = order_view(order)
        view.pop("history", None)
        return 202, {**view, "message": "Order accepted and is being processed"}

    def _replay(self, idem_id: str, request_hash: str) -> tuple[int, dict[str, Any]] | None:
        record = self.deps.orders.get_idempotency(idem_id)
        if not record:
            return None
        if record.get("requestHash") != request_hash:
            raise ConflictError(
                "Idempotency-Key was already used with a different request", code="IDEMPOTENCY_KEY_REUSED"
            )
        order = self.deps.orders.get(record["orderId"])
        if not order:
            raise TransientError("Order is being created, please retry")
        bind(orderId=order["orderId"])
        log.info("idempotent replay")
        return 200, {**order_view(order), "idempotentReplay": True}

    # -- reads --------------------------------------------------------------------
    def get_order(self, principal: Principal, order_id: str) -> dict[str, Any]:
        order = self.deps.orders.get(order_id)
        is_admin = principal.is_admin()
        # Customers get 404 (not 403) for other people's orders so ids cannot be probed.
        if not order or (order["customerId"] != principal.user_id and not is_admin):
            raise NotFoundError("Order not found")
        return order_view(order, admin=is_admin)

    def list_my_orders(self, principal: Principal, limit: int, token: str | None) -> dict[str, Any]:
        start = decode_token(token)
        if start and start.get("customerId") != principal.user_id:
            raise ValidationError("nextToken is invalid")
        items, last = self.deps.orders.list_for_customer(principal.user_id, limit, start)
        views = []
        for o in items:
            v = order_view(o)
            v.pop("history", None)
            views.append(v)
        return {"items": views, "nextToken": encode_token(last)}

    def list_notifications(self, principal: Principal, limit: int, token: str | None) -> dict[str, Any]:
        start = decode_token(token)
        if start and start.get("customerId") != principal.user_id:
            raise ValidationError("nextToken is invalid")
        items, last = self.deps.notifications.list_for_customer(principal.user_id, limit, start)
        return {"items": [notification_view(n) for n in items], "nextToken": encode_token(last)}
