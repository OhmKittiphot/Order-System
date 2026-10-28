"""Products (catalog) and Inventory (stock) persistence.

Catalog data and stock live in separate tables: product edits never race
with stock reservations, and inventory updates stay small and conditional.

Inventory item: ``productId, available, reserved, sold, version, updatedAt``
* ``available`` – can be sold now (never negative: every decrement is conditional)
* ``reserved``  – held by orders waiting for payment
* ``sold``      – committed by successful payments
"""

from __future__ import annotations

from typing import Any

from ..config.settings import Settings
from ..utils.common import now_iso
from .expressions import build_update
from .gateway import DynamoGateway
from .tables import CATALOG_INDEX


class CatalogRepository:
    def __init__(self, gw: DynamoGateway, settings: Settings) -> None:
        self.gw = gw
        self.products = settings.products_table
        self.inventory = settings.inventory_table

    # -- products ----------------------------------------------------------------
    def get_product(self, product_id: str) -> dict[str, Any] | None:
        return self.gw.get(self.products, {"productId": product_id})

    def get_products(self, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not product_ids:
            return {}
        items = self.gw.batch_get(self.products, [{"productId": p} for p in product_ids])
        return {i["productId"]: i for i in items}

    def list_active(self, limit: int, start: dict[str, Any] | None):  # type: ignore[no-untyped-def]
        return self.gw.query(
            self.products,
            index=CATALOG_INDEX,
            key_condition="#s = :s",
            names={"#s": "catalogStatus"},
            values={":s": "ACTIVE"},
            limit=limit,
            start_key=start,
        )

    def list_all(self, limit: int, start: dict[str, Any] | None):  # type: ignore[no-untyped-def]
        """Admin-only listing. A Scan is acceptable for a small catalog behind an
        admin route; customer-facing listing uses the catalog GSI."""
        return self.gw.scan(self.products, limit=limit, start_key=start)

    def create_product(self, product: dict[str, Any], initial_stock: int) -> None:
        now = product["createdAt"]
        self.gw.transact_write(
            [
                {
                    "Put": {
                        "TableName": self.products,
                        "Item": product,
                        "ConditionExpression": "attribute_not_exists(#k)",
                        "ExpressionAttributeNames": {"#k": "productId"},
                    }
                },
                {
                    "Put": {
                        "TableName": self.inventory,
                        "Item": {
                            "productId": product["productId"],
                            "available": initial_stock,
                            "reserved": 0,
                            "sold": 0,
                            "version": 1,
                            "updatedAt": now,
                        },
                        "ConditionExpression": "attribute_not_exists(#k)",
                        "ExpressionAttributeNames": {"#k": "productId"},
                    }
                },
            ]
        )

    def update_product(self, product_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        set_fields = {k: v for k, v in changes.items() if v is not None}
        remove = tuple(k for k, v in changes.items() if v is None)
        if "active" in changes:
            set_fields["catalogStatus"] = "ACTIVE" if changes["active"] else "INACTIVE"
        set_fields["updatedAt"] = now_iso()
        spec = build_update(set_fields=set_fields, remove=remove, increments={"version": 1}, must_exist="productId")
        return self.gw.update(
            self.products,
            {"productId": product_id},
            spec.update,
            condition=spec.condition,
            names=spec.names,
            values=spec.values,
        )

    # -- inventory ---------------------------------------------------------------
    def get_inventory(self, product_id: str) -> dict[str, Any] | None:
        return self.gw.get(self.inventory, {"productId": product_id})

    def get_inventories(self, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not product_ids:
            return {}
        items = self.gw.batch_get(self.inventory, [{"productId": p} for p in product_ids])
        return {i["productId"]: i for i in items}

    def scan_inventory(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        start = None
        while True:
            items, start = self.gw.scan(self.inventory, limit=200, start_key=start)
            out.extend(items)
            if not start:
                return out

    def set_available(self, product_id: str, quantity: int) -> dict[str, Any]:
        spec = build_update(
            set_fields={"available": quantity, "updatedAt": now_iso()},
            increments={"version": 1},
            must_exist="productId",
        )
        return self.gw.update(
            self.inventory,
            {"productId": product_id},
            spec.update,
            condition=spec.condition,
            names=spec.names,
            values=spec.values,
        )

    def adjust_available(self, product_id: str, delta: int) -> dict[str, Any]:
        """Atomic relative change; the condition prevents going below zero."""
        spec = build_update(
            set_fields={"updatedAt": now_iso()},
            increments={"available": delta, "version": 1},
            must_exist="productId",
            expect_at_least={"available": -delta} if delta < 0 else None,
        )
        return self.gw.update(
            self.inventory,
            {"productId": product_id},
            spec.update,
            condition=spec.condition,
            names=spec.names,
            values=spec.values,
        )

    # transaction building blocks ------------------------------------------------
    def reserve_op(self, product_id: str, qty: int) -> dict[str, Any]:
        spec = build_update(
            set_fields={"updatedAt": now_iso()},
            increments={"available": -qty, "reserved": qty, "version": 1},
            must_exist="productId",
            expect_at_least={"available": qty},
        )
        return spec.as_transact(self.inventory, {"productId": product_id})

    def commit_op(self, product_id: str, qty: int) -> dict[str, Any]:
        spec = build_update(
            set_fields={"updatedAt": now_iso()},
            increments={"reserved": -qty, "sold": qty, "version": 1},
            must_exist="productId",
            expect_at_least={"reserved": qty},
        )
        return spec.as_transact(self.inventory, {"productId": product_id})

    def release_op(self, product_id: str, qty: int) -> dict[str, Any]:
        spec = build_update(
            set_fields={"updatedAt": now_iso()},
            increments={"available": qty, "reserved": -qty, "version": 1},
            must_exist="productId",
            expect_at_least={"reserved": qty},
        )
        return spec.as_transact(self.inventory, {"productId": product_id})
