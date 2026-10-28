"""Shapes database records into API responses. Internal fields (outbox
tokens, test hooks, versions) are only exposed on admin views."""

from __future__ import annotations

from typing import Any

_ORDER_PUBLIC = (
    "orderId",
    "customerId",
    "items",
    "totalMinor",
    "currency",
    "itemCount",
    "status",
    "inventoryStatus",
    "paymentStatus",
    "notificationStatus",
    "failureReason",
    "failureCategory",
    "createdAt",
    "updatedAt",
    "history",
    "attempt",
)
_ORDER_ADMIN_EXTRA = (
    "idempotencyKey",
    "processingAttempts",
    "version",
    "lastRetryAt",
    "lastRetryBy",
    "lastPublishedAt",
    "outboxStatus",
    "outboxEventType",
    "correlationId",
    "cancelledBy",
)


def order_view(order: dict[str, Any], *, admin: bool = False) -> dict[str, Any]:
    keys = _ORDER_PUBLIC + (_ORDER_ADMIN_EXTRA if admin else ())
    view = {k: order[k] for k in keys if k in order}
    items = []
    for line in order.get("items", []):
        line_view = {k: v for k, v in line.items() if admin or k != "testBehavior"}
        items.append(line_view)
    view["items"] = items
    view["retryCount"] = int(order.get("attempt", 0))
    return view


def product_view(product: dict[str, Any], inventory: dict[str, Any] | None, *, admin: bool = False) -> dict[str, Any]:
    available = int(inventory.get("available", 0)) if inventory else 0
    view: dict[str, Any] = {
        "productId": product["productId"],
        "name": product.get("name", ""),
        "description": product.get("description", ""),
        "priceMinor": int(product.get("priceMinor", 0)),
        "currency": product.get("currency", "THB"),
        "category": product.get("category", "General"),
        "imageUrl": product.get("imageUrl"),
        "available": available,
        "inStock": available > 0,
    }
    if admin:
        view.update(
            {
                "active": bool(product.get("active", False)),
                "reserved": int(inventory.get("reserved", 0)) if inventory else 0,
                "sold": int(inventory.get("sold", 0)) if inventory else 0,
                "testBehavior": product.get("testBehavior"),
                "createdAt": product.get("createdAt"),
                "updatedAt": product.get("updatedAt"),
                "inventoryUpdatedAt": inventory.get("updatedAt") if inventory else None,
            }
        )
    return view


def notification_view(n: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "notificationId",
        "orderId",
        "type",
        "orderStatus",
        "title",
        "message",
        "createdAt",
        "channels",
        "emailStatus",
    )
    return {k: n[k] for k in keys if k in n}


def money(minor: int, currency: str) -> str:
    return f"{minor / 100:,.2f} {currency}"
