"""Payments, Notifications and Users persistence."""

from __future__ import annotations

from typing import Any

from ..config.settings import Settings
from ..utils.common import now_iso
from ..utils.errors import ConditionFailedError, ConflictError, TransactionCanceledError
from .expressions import build_update
from .gateway import DynamoGateway
from .tables import NOTIFY_CUSTOMER_INDEX


class PaymentsRepository:
    """One payment record per (orderId, attempt). The conditional put makes a
    duplicate event unable to create a second payment for the same attempt."""

    def __init__(self, gw: DynamoGateway, settings: Settings) -> None:
        self.gw = gw
        self.table = settings.payments_table

    def put_op(self, payment: dict[str, Any]) -> dict[str, Any]:
        return {
            "Put": {
                "TableName": self.table,
                "Item": payment,
                "ConditionExpression": "attribute_not_exists(#k)",
                "ExpressionAttributeNames": {"#k": "orderId"},
            }
        }

    def list_for_order(self, order_id: str) -> list[dict[str, Any]]:
        items, _ = self.gw.query(
            self.table, key_condition="#o = :o", names={"#o": "orderId"}, values={":o": order_id}, consistent=True
        )
        return items


class NotificationsRepository:
    def __init__(self, gw: DynamoGateway, settings: Settings) -> None:
        self.gw = gw
        self.table = settings.notifications_table

    def create_if_absent(self, notification: dict[str, Any]) -> bool:
        """Returns False if this logical notification already exists (dedupe)."""
        try:
            self.gw.put(
                self.table,
                notification,
                condition="attribute_not_exists(#k)",
                names={"#k": "notificationId"},
            )
            return True
        except ConditionFailedError:
            return False

    def get(self, notification_id: str) -> dict[str, Any] | None:
        return self.gw.get(self.table, {"notificationId": notification_id})

    def mark_email(self, notification_id: str, status: str, message_id: str | None = None) -> None:
        fields: dict[str, Any] = {"emailStatus": status, "emailUpdatedAt": now_iso()}
        if message_id:
            fields["snsMessageId"] = message_id
        spec = build_update(set_fields=fields, increments={"emailAttempts": 1}, must_exist="notificationId")
        self.gw.update(
            self.table,
            {"notificationId": notification_id},
            spec.update,
            condition=spec.condition,
            names=spec.names,
            values=spec.values,
        )

    def list_for_customer(self, customer_id: str, limit: int, start: dict[str, Any] | None):  # type: ignore[no-untyped-def]
        return self.gw.query(
            self.table,
            index=NOTIFY_CUSTOMER_INDEX,
            key_condition="#c = :c",
            names={"#c": "customerId"},
            values={":c": customer_id},
            limit=limit,
            start_key=start,
            forward=False,
        )


class UsersRepository:
    """Users table, two item types sharing the ``userId`` key:

    * profile    ``userId = <uuid>`` – email, displayName, role, timestamps.
    * credential ``userId = "EMAIL#<email>"`` – ownerId + passwordHash. Keyed by
      email so the conditional put makes emails unique and login is a GetItem.
      The hash is never returned by the API.
    """

    CREDENTIAL_PREFIX = "EMAIL#"

    def __init__(self, gw: DynamoGateway, settings: Settings) -> None:
        self.gw = gw
        self.table = settings.users_table

    def get(self, user_id: str) -> dict[str, Any] | None:
        return self.gw.get(self.table, {"userId": user_id})

    def get_credential(self, email: str) -> dict[str, Any] | None:
        return self.gw.get(self.table, {"userId": self.CREDENTIAL_PREFIX + email})

    def create(self, profile: dict[str, Any], password_hash: str) -> None:
        """Profile + credential in one transaction; ConflictError if the email is taken."""
        credential = {
            "userId": self.CREDENTIAL_PREFIX + profile["email"],
            "entityType": "CREDENTIAL",
            "ownerId": profile["userId"],
            "passwordHash": password_hash,
            "createdAt": profile["createdAt"],
        }
        try:
            self.gw.transact_write(
                [
                    {
                        "Put": {
                            "TableName": self.table,
                            "Item": item,
                            "ConditionExpression": "attribute_not_exists(#k)",
                            "ExpressionAttributeNames": {"#k": "userId"},
                        }
                    }
                    for item in ({**profile, "entityType": "USER"}, credential)
                ]
            )
        except TransactionCanceledError as exc:
            if exc.failed_indexes():
                raise ConflictError("An account with this email already exists", code="EMAIL_EXISTS") from exc
            raise

    def update_fields(self, user_id: str, fields: dict[str, Any]) -> None:
        spec = build_update(set_fields={**fields, "updatedAt": now_iso()}, must_exist="userId")
        self.gw.update(
            self.table, {"userId": user_id}, spec.update, condition=spec.condition, names=spec.names, values=spec.values
        )
