"""Admin read models: dashboard stats, order detail, operational status."""

from __future__ import annotations

from typing import Any

from ..models.order_states import OrderStatus
from ..utils.common import decode_token, encode_token, iso_seconds_ago, now_iso
from ..utils.errors import NotFoundError, ValidationError
from ..utils.logging import get_logger
from .catalog_service import CatalogService
from .container import Deps
from .retry_service import RetryService
from .views import order_view

log = get_logger("admin-service")


class AdminService:
    def __init__(self, deps: Deps) -> None:
        self.deps = deps
        self.settings = deps.settings

    def list_orders(self, limit: int, token: str | None, status: str | None) -> dict[str, Any]:
        start = decode_token(token)
        if start and status and start.get("status") != status:
            raise ValidationError("nextToken does not match the status filter")
        items, last = self.deps.orders.list_all(limit, start, status)
        retry = RetryService(self.deps)
        out = []
        for o in items:
            v = order_view(o, admin=True)
            v.pop("history", None)
            v["retry"] = (
                retry.classify(o)
                if o["status"] in (OrderStatus.FAILED, OrderStatus.PENDING, OrderStatus.PROCESSING)
                else None
            )
            out.append(v)
        return {"items": out, "nextToken": encode_token(last)}

    def order_detail(self, order_id: str) -> dict[str, Any]:
        order = self.deps.orders.get(order_id)
        if not order:
            raise NotFoundError("Order not found")
        view = order_view(order, admin=True)
        view["payments"] = self.deps.payments.list_for_order(order_id)
        view["retry"] = RetryService(self.deps).classify(order)
        user = self.deps.users.get(order["customerId"])
        view["customer"] = {"userId": order["customerId"], "displayName": (user or {}).get("displayName")}
        return view

    def stats(self) -> dict[str, Any]:
        counts = {s: self.deps.orders.count_by_status(s) for s in OrderStatus.ALL}
        inventory = self.deps.catalog.scan_inventory()
        low = CatalogService(self.deps).low_stock()
        return {
            "orders": {"total": sum(counts.values()), "byStatus": counts},
            "products": {
                "total": len(inventory),
                "lowStock": len(low),
                "lowStockThreshold": self.settings.low_stock_threshold,
            },
            "lowStockProducts": low[:10],
            "generatedAt": now_iso(),
        }

    def dlq_status(self) -> dict[str, Any]:
        queues: list[dict[str, Any]] = []
        for name in ("stock", "payment", "notify"):
            cfg = self.settings.queues.get(name)
            entry: dict[str, Any] = {"name": name, "configured": bool(cfg)}
            if cfg and self.deps.queues is not None:
                try:
                    q = self.deps.queues.attributes(cfg.queue_url)
                    d = self.deps.queues.attributes(cfg.dlq_url)
                    entry.update(
                        queueVisible=q.get("ApproximateNumberOfMessages", 0),
                        queueInFlight=q.get("ApproximateNumberOfMessagesNotVisible", 0),
                        dlqVisible=d.get("ApproximateNumberOfMessages", 0),
                        dlqInFlight=d.get("ApproximateNumberOfMessagesNotVisible", 0),
                    )
                except Exception as exc:  # noqa: BLE001 - show partial status instead of failing the page
                    entry["error"] = f"Could not read queue attributes ({type(exc).__name__})"
            queues.append(entry)

        alarms: list[dict[str, Any]] = []
        if self.deps.alarms is not None and self.settings.alarm_name_prefix:
            try:
                alarms = self.deps.alarms.alarms(self.settings.alarm_name_prefix)
            except Exception as exc:  # noqa: BLE001
                log.warning("describe alarms failed", error=type(exc).__name__)

        cutoff = iso_seconds_ago(self.settings.stuck_order_seconds)
        stuck = self.deps.orders.list_stuck(OrderStatus.PENDING, cutoff) + self.deps.orders.list_stuck(
            OrderStatus.PROCESSING, cutoff
        )
        failed, _ = self.deps.orders.list_all(20, None, OrderStatus.FAILED)
        retry = RetryService(self.deps)
        return {
            "queues": queues,
            "alarms": alarms,
            "stuckOrders": [
                {
                    "orderId": o["orderId"],
                    "status": o["status"],
                    "updatedAt": o["updatedAt"],
                    "retry": retry.classify(o),
                }
                for o in stuck[:20]
            ],
            "recentFailedOrders": [
                {
                    "orderId": o["orderId"],
                    "failureCategory": o.get("failureCategory"),
                    "failureReason": o.get("failureReason"),
                    "updatedAt": o["updatedAt"],
                    "retry": retry.classify(o),
                }
                for o in failed
            ],
            "note": "SQS counts are approximate and CloudWatch alarm states can lag by a few minutes.",
            "generatedAt": now_iso(),
        }
