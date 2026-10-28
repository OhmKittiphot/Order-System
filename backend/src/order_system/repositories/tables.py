"""DynamoDB table layouts (keys and GSIs). Must match terraform/dynamodb.tf.

The local in-memory gateway builds its tables from this description, so a
key/index mismatch between code and tests is impossible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config.settings import Settings

# Orders indexes
CUSTOMER_INDEX = "customer-index"  # customerId + createdAt -> customer history
ENTITY_INDEX = "entity-index"  # entityType("ORDER") + createdAt -> admin list
STATUS_INDEX = "status-index"  # status + createdAt -> admin filter / stats
OUTBOX_INDEX = "outbox-index"  # outboxStatus (sparse) + createdAt -> unpublished events
# Products index
CATALOG_INDEX = "catalog-index"  # catalogStatus + name -> public catalog
# Notifications index
NOTIFY_CUSTOMER_INDEX = "customer-index"  # customerId + createdAt


@dataclass(frozen=True)
class TableLayout:
    logical: str
    partition_key: str
    sort_key: str | None = None
    indexes: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    ttl_attribute: str | None = None


LAYOUTS: dict[str, TableLayout] = {
    "orders": TableLayout(
        "orders",
        "orderId",
        indexes={
            CUSTOMER_INDEX: ("customerId", "createdAt"),
            ENTITY_INDEX: ("entityType", "createdAt"),
            STATUS_INDEX: ("status", "createdAt"),
            OUTBOX_INDEX: ("outboxStatus", "createdAt"),
        },
    ),
    "products": TableLayout("products", "productId", indexes={CATALOG_INDEX: ("catalogStatus", "name")}),
    "inventory": TableLayout("inventory", "productId"),
    "payments": TableLayout("payments", "orderId", "attempt"),
    "notifications": TableLayout(
        "notifications", "notificationId", indexes={NOTIFY_CUSTOMER_INDEX: ("customerId", "createdAt")}
    ),
    "users": TableLayout("users", "userId"),
    "idempotency": TableLayout("idempotency", "idempotencyId", ttl_attribute="expiresAt"),
}


def physical_name(settings: Settings, logical: str) -> str:
    return {
        "orders": settings.orders_table,
        "products": settings.products_table,
        "inventory": settings.inventory_table,
        "payments": settings.payments_table,
        "notifications": settings.notifications_table,
        "users": settings.users_table,
        "idempotency": settings.idempotency_table,
    }[logical]
