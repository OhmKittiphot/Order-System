"""Thin DynamoDB gateway.

Repositories talk to this small interface with plain Python values
(``str``, ``int``, ``bool``, ``list``, ``dict``, ``None``). The real
implementation (``BotoDynamoGateway``) serialises to DynamoDB's typed
format with boto3's ``TypeSerializer``; tests and the local dev server use
an in-memory implementation with the same interface and the same
condition/update-expression semantics (``order_system_local.memory_dynamo``).

All numbers stored by this application are integers (money is kept in
minor units), so numbers read back are converted to ``int``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from ..utils.errors import (
    ConditionFailedError,
    TransactionCanceledError,
    TransientError,
)

Item = dict[str, Any]


class DynamoGateway(Protocol):
    def get(self, table: str, key: Item, *, consistent: bool = True) -> Item | None: ...

    def put(
        self,
        table: str,
        item: Item,
        *,
        condition: str | None = None,
        names: dict[str, str] | None = None,
        values: dict[str, Any] | None = None,
    ) -> None: ...

    def update(
        self,
        table: str,
        key: Item,
        update: str,
        *,
        condition: str | None = None,
        names: dict[str, str] | None = None,
        values: dict[str, Any] | None = None,
    ) -> Item: ...

    def query(
        self,
        table: str,
        *,
        key_condition: str,
        names: dict[str, str] | None = None,
        values: dict[str, Any] | None = None,
        index: str | None = None,
        filter_expression: str | None = None,
        limit: int | None = None,
        start_key: Item | None = None,
        forward: bool = True,
        consistent: bool = False,
    ) -> tuple[list[Item], Item | None]: ...

    def count(
        self,
        table: str,
        *,
        key_condition: str,
        names: dict[str, str] | None = None,
        values: dict[str, Any] | None = None,
        index: str | None = None,
    ) -> int: ...

    def scan(
        self,
        table: str,
        *,
        limit: int | None = None,
        start_key: Item | None = None,
    ) -> tuple[list[Item], Item | None]: ...

    def batch_get(self, table: str, keys: list[Item]) -> list[Item]: ...

    def transact_write(self, operations: list[dict[str, Any]]) -> None: ...


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    if isinstance(value, set):
        return [_from_dynamo(v) for v in value]
    return value


class BotoDynamoGateway:
    """boto3 implementation. Imported lazily so unit tests need no boto3."""

    _RETRYABLE = {
        "ProvisionedThroughputExceededException",
        "ThrottlingException",
        "RequestLimitExceeded",
        "InternalServerError",
        "TransactionInProgressException",
    }

    def __init__(self, client: Any = None) -> None:
        import boto3
        from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
        from botocore.config import Config

        self._client = client or boto3.client(
            "dynamodb", config=Config(retries={"max_attempts": 5, "mode": "standard"})
        )
        self._ser = TypeSerializer()
        self._de = TypeDeserializer()

    # -- serialisation ------------------------------------------------------
    def _s(self, item: Item) -> dict[str, Any]:
        return {k: self._ser.serialize(v) for k, v in item.items()}

    def _d(self, item: dict[str, Any] | None) -> Item | None:
        if item is None:
            return None
        return {k: _from_dynamo(self._de.deserialize(v)) for k, v in item.items()}

    def _expr(self, names: dict[str, str] | None, values: dict[str, Any] | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if names:
            out["ExpressionAttributeNames"] = names
        if values:
            out["ExpressionAttributeValues"] = self._s(values)
        return out

    def _call(self, fn: Any, **kwargs: Any) -> Any:
        from botocore.exceptions import ClientError

        try:
            return fn(**kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                raise ConditionFailedError(str(exc)) from exc
            if code == "TransactionCanceledException":
                reasons = [r.get("Code") for r in exc.response.get("CancellationReasons", [])]
                raise TransactionCanceledError(reasons) from exc
            if code in self._RETRYABLE:
                raise TransientError(f"DynamoDB temporarily unavailable: {code}") from exc
            raise

    # -- operations ---------------------------------------------------------
    def get(self, table: str, key: Item, *, consistent: bool = True) -> Item | None:
        res = self._call(self._client.get_item, TableName=table, Key=self._s(key), ConsistentRead=consistent)
        return self._d(res.get("Item"))

    def put(self, table, item, *, condition=None, names=None, values=None) -> None:  # type: ignore[no-untyped-def]
        kwargs: dict[str, Any] = {"TableName": table, "Item": self._s(item), **self._expr(names, values)}
        if condition:
            kwargs["ConditionExpression"] = condition
        self._call(self._client.put_item, **kwargs)

    def update(self, table, key, update, *, condition=None, names=None, values=None) -> Item:  # type: ignore[no-untyped-def]
        kwargs: dict[str, Any] = {
            "TableName": table,
            "Key": self._s(key),
            "UpdateExpression": update,
            "ReturnValues": "ALL_NEW",
            **self._expr(names, values),
        }
        if condition:
            kwargs["ConditionExpression"] = condition
        res = self._call(self._client.update_item, **kwargs)
        return self._d(res.get("Attributes")) or {}

    def query(  # type: ignore[no-untyped-def]
        self,
        table,
        *,
        key_condition,
        names=None,
        values=None,
        index=None,
        filter_expression=None,
        limit=None,
        start_key=None,
        forward=True,
        consistent=False,
    ):
        kwargs: dict[str, Any] = {
            "TableName": table,
            "KeyConditionExpression": key_condition,
            "ScanIndexForward": forward,
            **self._expr(names, values),
        }
        if index:
            kwargs["IndexName"] = index
        else:
            kwargs["ConsistentRead"] = consistent
        if filter_expression:
            kwargs["FilterExpression"] = filter_expression
        if limit:
            kwargs["Limit"] = limit
        if start_key:
            kwargs["ExclusiveStartKey"] = self._s(start_key)
        res = self._call(self._client.query, **kwargs)
        items = [self._d(i) or {} for i in res.get("Items", [])]
        return items, self._d(res.get("LastEvaluatedKey"))

    def count(self, table, *, key_condition, names=None, values=None, index=None) -> int:  # type: ignore[no-untyped-def]
        total = 0
        start: dict[str, Any] | None = None
        while True:
            kwargs: dict[str, Any] = {
                "TableName": table,
                "KeyConditionExpression": key_condition,
                "Select": "COUNT",
                **self._expr(names, values),
            }
            if index:
                kwargs["IndexName"] = index
            if start:
                kwargs["ExclusiveStartKey"] = start
            res = self._call(self._client.query, **kwargs)
            total += int(res.get("Count", 0))
            start = res.get("LastEvaluatedKey")
            if not start:
                return total

    def scan(self, table, *, limit=None, start_key=None):  # type: ignore[no-untyped-def]
        kwargs: dict[str, Any] = {"TableName": table}
        if limit:
            kwargs["Limit"] = limit
        if start_key:
            kwargs["ExclusiveStartKey"] = self._s(start_key)
        res = self._call(self._client.scan, **kwargs)
        return [self._d(i) or {} for i in res.get("Items", [])], self._d(res.get("LastEvaluatedKey"))

    def batch_get(self, table: str, keys: list[Item]) -> list[Item]:
        out: list[Item] = []
        for i in range(0, len(keys), 100):
            pending: dict[str, Any] = {table: {"Keys": [self._s(k) for k in keys[i : i + 100]]}}
            for _ in range(5):
                res = self._call(self._client.batch_get_item, RequestItems=pending)
                out.extend(self._d(x) or {} for x in res.get("Responses", {}).get(table, []))
                pending = res.get("UnprocessedKeys") or {}
                if not pending:
                    break
            if pending:
                raise TransientError("DynamoDB BatchGetItem left unprocessed keys")
        return out

    def transact_write(self, operations: list[dict[str, Any]]) -> None:
        typed: list[dict[str, Any]] = []
        for op in operations:
            ((kind, body),) = op.items()
            body = dict(body)
            if "Item" in body:
                body["Item"] = self._s(body["Item"])
            if "Key" in body:
                body["Key"] = self._s(body["Key"])
            if "ExpressionAttributeValues" in body:
                body["ExpressionAttributeValues"] = self._s(body["ExpressionAttributeValues"])
            typed.append({kind: body})
        self._call(self._client.transact_write_items, TransactItems=typed)
