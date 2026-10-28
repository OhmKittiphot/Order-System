"""Product catalog and inventory management."""

from __future__ import annotations

from typing import Any

from ..utils.common import decode_token, encode_token, new_id, now_iso
from ..utils.errors import (
    ConditionFailedError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from ..utils.logging import get_logger
from .container import Deps
from .views import product_view

log = get_logger("catalog-service")


class CatalogService:
    def __init__(self, deps: Deps) -> None:
        self.deps = deps
        self.repo = deps.catalog
        self.settings = deps.settings

    # -- public ---------------------------------------------------------------------
    def list_products(self, limit: int, token: str | None) -> dict[str, Any]:
        start = decode_token(token)
        if start and start.get("catalogStatus") != "ACTIVE":
            raise ValidationError("nextToken is invalid")
        products, last = self.repo.list_active(limit, start)
        stock = self.repo.get_inventories([p["productId"] for p in products])
        return {
            "items": [product_view(p, stock.get(p["productId"])) for p in products],
            "nextToken": encode_token(last),
        }

    def get_product(self, product_id: str) -> dict[str, Any]:
        product = self.repo.get_product(product_id)
        if not product or not product.get("active"):
            raise NotFoundError("Product not found")
        return product_view(product, self.repo.get_inventory(product_id))

    # -- admin ----------------------------------------------------------------------
    def admin_list(self, limit: int, token: str | None) -> dict[str, Any]:
        products, last = self.repo.list_all(limit, decode_token(token))
        stock = self.repo.get_inventories([p["productId"] for p in products])
        items = [product_view(p, stock.get(p["productId"]), admin=True) for p in products]
        items.sort(key=lambda p: p["name"].lower())
        return {"items": items, "nextToken": encode_token(last), "lowStockThreshold": self.settings.low_stock_threshold}

    def admin_get(self, product_id: str) -> dict[str, Any]:
        product = self.repo.get_product(product_id)
        if not product:
            raise NotFoundError("Product not found")
        return product_view(product, self.repo.get_inventory(product_id), admin=True)

    def create(self, data: dict[str, Any], admin_id: str) -> dict[str, Any]:
        now = now_iso()
        product: dict[str, Any] = {
            "productId": new_id("prd"),
            "name": data["name"],
            "description": data["description"],
            "priceMinor": data["priceMinor"],
            "currency": self.settings.currency,
            "category": data["category"],
            "active": data["active"],
            "catalogStatus": "ACTIVE" if data["active"] else "INACTIVE",
            "createdAt": now,
            "updatedAt": now,
            "createdBy": admin_id,
            "version": 1,
        }
        if data.get("imageUrl"):
            product["imageUrl"] = data["imageUrl"]
        if data.get("testBehavior"):
            product["testBehavior"] = data["testBehavior"]
        self.repo.create_product(product, data["initialStock"])
        log.info("product created", productId=product["productId"], initialStock=data["initialStock"])
        return self.admin_get(product["productId"])

    def update(self, product_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        try:
            self.repo.update_product(product_id, changes)
        except ConditionFailedError as exc:
            raise NotFoundError("Product not found") from exc
        log.info("product updated", productId=product_id, fields=sorted(changes))
        return self.admin_get(product_id)

    def change_stock(self, product_id: str, mode: str, quantity: int, reason: str, admin_id: str) -> dict[str, Any]:
        if not self.repo.get_product(product_id):
            raise NotFoundError("Product not found")
        try:
            if mode == "set":
                self.repo.set_available(product_id, quantity)
            else:
                self.repo.adjust_available(product_id, quantity)
        except ConditionFailedError as exc:
            if self.repo.get_inventory(product_id) is None:
                raise NotFoundError("Inventory record not found") from exc
            raise ConflictError("Stock cannot go below zero", code="NEGATIVE_STOCK") from exc
        log.info("stock changed", productId=product_id, mode=mode, quantity=quantity, reason=reason, adminId=admin_id)
        return self.admin_get(product_id)

    def low_stock(self) -> list[dict[str, Any]]:
        inventory = self.repo.scan_inventory()
        low = [i for i in inventory if int(i.get("available", 0)) <= self.settings.low_stock_threshold]
        products = self.repo.get_products([i["productId"] for i in low])
        return [
            product_view(products[i["productId"]], i, admin=True)
            for i in low
            if i["productId"] in products and products[i["productId"]].get("active")
        ]
