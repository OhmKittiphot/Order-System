"""Orders + Idempotency persistence."""

from __future__ import annotations

import contextlib
from typing import Any

from ..config.settings import Settings
from ..utils.common import now_iso
from ..utils.errors import ConditionFailedError
from .expressions import UpdateSpec, build_update
from .gateway import DynamoGateway
from .tables import CUSTOMER_INDEX, ENTITY_INDEX, OUTBOX_INDEX, STATUS_INDEX

OUTBOX_PENDING = "PENDING_PUBLISH"


def history_entry(event: str, detail: str = "", status: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"at": now_iso(), "event": event}
    if detail:
        entry["detail"] = detail
    if status:
        entry["status"] = status
    return entry


class OrdersRepository:
    def __init__(self, gw: DynamoGateway, settings: Settings) -> None:
        self.gw = gw
        self.table = settings.orders_table
        self.idem_table = settings.idempotency_table

    # -- reads -----------------------------------------------------------------
    def get(self, order_id: str) -> dict[str, Any] | None:
        return self.gw.get(self.table, {"orderId": order_id})

    def get_idempotency(self, idempotency_id: str) -> dict[str, Any] | None:
        return self.gw.get(self.idem_table, {"idempotencyId": idempotency_id})

    def list_for_customer(self, customer_id: str, limit: int, start: dict[str, Any] | None):  # type: ignore[no-untyped-def]
        return self.gw.query(
            self.table,
            index=CUSTOMER_INDEX,
            key_condition="#c = :c",
            names={"#c": "customerId"},
            values={":c": customer_id},
            limit=limit,
            start_key=start,
            forward=False,
        )

    def list_all(self, limit: int, start: dict[str, Any] | None, status: str | None = None):  # type: ignore[no-untyped-def]
        if status:
            return self.gw.query(
                self.table,
                index=STATUS_INDEX,
                key_condition="#s = :s",
                names={"#s": "status"},
                values={":s": status},
                limit=limit,
                start_key=start,
                forward=False,
            )
        return self.gw.query(
            self.table,
            index=ENTITY_INDEX,
            key_condition="#e = :e",
            names={"#e": "entityType"},
            values={":e": "ORDER"},
            limit=limit,
            start_key=start,
            forward=False,
        )

    def count_by_status(self, status: str) -> int:
        return self.gw.count(
            self.table, index=STATUS_INDEX, key_condition="#s = :s", names={"#s": "status"}, values={":s": status}
        )

    def list_outbox(self, created_before: str, limit: int = 50) -> list[dict[str, Any]]:
        items, _ = self.gw.query(
            self.table,
            index=OUTBOX_INDEX,
            key_condition="#o = :o AND #c <= :t",
            names={"#o": "outboxStatus", "#c": "createdAt"},
            values={":o": OUTBOX_PENDING, ":t": created_before},
            limit=limit,
        )
        return items

    def list_stuck(self, status: str, updated_before: str, limit: int = 50) -> list[dict[str, Any]]:
        items, _ = self.gw.query(
            self.table,
            index=STATUS_INDEX,
            key_condition="#s = :s",
            filter_expression="#u <= :t",
            names={"#s": "status", "#u": "updatedAt"},
            values={":s": status, ":t": updated_before},
            limit=limit,
        )
        return items

    # -- writes ----------------------------------------------------------------
    def create_with_idempotency(self, order: dict[str, Any], idempotency: dict[str, Any]) -> None:
        """Atomically claim the idempotency key and create the order."""
        self.gw.transact_write(
            [
                {
                    "Put": {
                        "TableName": self.idem_table,
                        "Item": idempotency,
                        "ConditionExpression": "attribute_not_exists(#k)",
                        "ExpressionAttributeNames": {"#k": "idempotencyId"},
                    }
                },
                {
                    "Put": {
                        "TableName": self.table,
                        "Item": order,
                        "ConditionExpression": "attribute_not_exists(#k)",
                        "ExpressionAttributeNames": {"#k": "orderId"},
                    }
                },
            ]
        )

    def transition_spec(
        self,
        *,
        expect: dict[str, Any],
        set_fields: dict[str, Any],
        history: dict[str, Any] | None = None,
        remove: tuple[str, ...] = (),
        expect_in: dict[str, list[Any]] | None = None,
        extra_condition: str | None = None,
        extra_names: dict[str, str] | None = None,
        extra_values: dict[str, Any] | None = None,
        increments: dict[str, int] | None = None,
    ) -> UpdateSpec:
        fields = dict(set_fields)
        fields.setdefault("updatedAt", now_iso())
        inc = {"version": 1}
        inc.update(increments or {})
        return build_update(
            set_fields=fields,
            increments=inc,
            remove=remove,
            append={"history": [history]} if history else None,
            must_exist="orderId",
            expect_equal=expect,
            expect_in=expect_in,
            extra_condition=extra_condition,
            extra_names=extra_names,
            extra_values=extra_values,
        )

    def transition_op(self, order_id: str, spec: UpdateSpec) -> dict[str, Any]:
        return spec.as_transact(self.table, {"orderId": order_id})

    def apply(self, order_id: str, spec: UpdateSpec) -> dict[str, Any]:
        return self.gw.update(
            self.table,
            {"orderId": order_id},
            spec.update,
            condition=spec.condition,
            names=spec.names,
            values=spec.values,
        )

    def add_processing_attempt(self, order_id: str) -> None:
        """Counts every time a worker starts processing this order (including
        SQS redeliveries). Does not bump ``version``: it is diagnostic only."""
        spec = build_update(increments={"processingAttempts": 1}, must_exist="orderId")
        with contextlib.suppress(ConditionFailedError):
            self.apply(order_id, spec)

    def clear_outbox(self, order_id: str, outbox_token: str) -> bool:
        """Remove the outbox marker once the event was published. The token
        guards against clearing a newer marker written by an admin retry."""
        spec = build_update(
            set_fields={"lastPublishedAt": now_iso()},
            remove=("outboxStatus", "outboxEventType", "outboxToken"),
            must_exist="outboxStatus",
            expect_equal={"outboxToken": outbox_token},
        )
        try:
            self.apply(order_id, spec)
            return True
        except ConditionFailedError:
            return False
