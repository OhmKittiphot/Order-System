"""Unit tests for pure helpers, the state machine and the DynamoDB emulator."""

from __future__ import annotations

import pytest

from order_system.config.settings import Settings
from order_system.models.order_states import TRANSITIONS, OrderStatus, is_allowed
from order_system.schemas.validation import (
    validate_create_order,
    validate_product_update,
    validate_stock_change,
)
from order_system.utils.common import decode_token, encode_token, retry_with_backoff
from order_system.utils.errors import (
    ConditionFailedError,
    TransactionCanceledError,
    ValidationError,
)
from order_system_local.memory_dynamo import MemoryDynamoGateway, TableDef


def test_state_machine_transitions():
    assert is_allowed(OrderStatus.PENDING, OrderStatus.PROCESSING)
    assert is_allowed(OrderStatus.PROCESSING, OrderStatus.CONFIRMED)
    assert not is_allowed(OrderStatus.PENDING, OrderStatus.CONFIRMED)  # payment cannot be skipped
    assert not is_allowed(OrderStatus.CONFIRMED, OrderStatus.FAILED)
    assert not any(src == OrderStatus.CONFIRMED for src, _ in TRANSITIONS)
    assert not any(src == OrderStatus.CANCELLED for src, _ in TRANSITIONS)


def test_order_validation_limits():
    s = Settings(max_order_items=2)
    with pytest.raises(ValidationError):
        validate_create_order({"items": [{"productId": f"prd_{i}x", "quantity": 1} for i in range(3)]}, s)
    with pytest.raises(ValidationError):
        validate_create_order(
            {"items": [{"productId": "prd_abc", "quantity": 60}, {"productId": "prd_abc", "quantity": 60}]}, s
        )
    assert validate_create_order({"items": [{"productId": "prd_abc", "quantity": 2}]}, s) == [("prd_abc", 2)]


def test_product_and_stock_validation():
    with pytest.raises(ValidationError):
        validate_product_update({})
    with pytest.raises(ValidationError):
        validate_product_update({"testBehavior": "DROP_TABLE"})
    assert validate_product_update({"testBehavior": None}) == {"testBehavior": None}
    assert validate_stock_change({"mode": "adjust", "quantity": -3}) == ("adjust", -3, "")
    with pytest.raises(ValidationError):
        validate_stock_change({"mode": "adjust", "quantity": 0})


def test_pagination_token_roundtrip_and_tamper():
    key = {"orderId": "ord_1", "customerId": "c", "createdAt": "2026"}
    assert decode_token(encode_token(key)) == key
    with pytest.raises(ValidationError):
        decode_token("eyJub3QiOlsibGlzdCJdfQ")  # {"not":["list"]}


def test_retry_with_backoff_eventually_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("x")
        return "ok"

    delays = []
    assert retry_with_backoff(flaky, attempts=3, sleep=delays.append) == "ok"
    assert len(delays) == 2 and all(0 <= d <= 1.0 for d in delays)


# --- emulator self-tests (so we can trust the other tests) -------------------


def _gw():
    return MemoryDynamoGateway([TableDef("t", "pk")])


def test_emulator_conditional_put_and_update():
    gw = _gw()
    gw.put("t", {"pk": "a", "n": 1, "status": "X"})
    with pytest.raises(ConditionFailedError):
        gw.put("t", {"pk": "a"}, condition="attribute_not_exists(#k)", names={"#k": "pk"})
    new = gw.update(
        "t",
        {"pk": "a"},
        "SET #n = #n + :d",
        condition="#s = :x AND #n >= :one",
        names={"#n": "n", "#s": "status"},
        values={":d": 2, ":x": "X", ":one": 1},
    )
    assert new["n"] == 3
    with pytest.raises(ConditionFailedError):
        gw.update(
            "t",
            {"pk": "a"},
            "SET #n = :z",
            condition="#n IN (:a, :b)",
            names={"#n": "n"},
            values={":z": 0, ":a": 1, ":b": 2},
        )


def test_emulator_transaction_is_all_or_nothing():
    gw = _gw()
    gw.put("t", {"pk": "a", "n": 5})
    gw.put("t", {"pk": "b", "n": 0})
    ops = [
        {
            "Update": {
                "TableName": "t",
                "Key": {"pk": "a"},
                "UpdateExpression": "SET #n = #n - :q",
                "ConditionExpression": "#n >= :q",
                "ExpressionAttributeNames": {"#n": "n"},
                "ExpressionAttributeValues": {":q": 1},
            }
        },
        {
            "Update": {
                "TableName": "t",
                "Key": {"pk": "b"},
                "UpdateExpression": "SET #n = #n - :q",
                "ConditionExpression": "#n >= :q",
                "ExpressionAttributeNames": {"#n": "n"},
                "ExpressionAttributeValues": {":q": 1},
            }
        },
    ]
    with pytest.raises(TransactionCanceledError) as err:
        gw.transact_write(ops)
    assert err.value.reasons == ["None", "ConditionalCheckFailed"]
    assert gw.get("t", {"pk": "a"})["n"] == 5  # rolled back


def test_emulator_rejects_two_ops_on_same_item_and_unused_placeholders():
    gw = _gw()
    gw.put("t", {"pk": "a", "n": 1})
    op = {
        "Update": {
            "TableName": "t",
            "Key": {"pk": "a"},
            "UpdateExpression": "SET #n = :v",
            "ExpressionAttributeNames": {"#n": "n"},
            "ExpressionAttributeValues": {":v": 2},
        }
    }
    with pytest.raises(ValueError):
        gw.transact_write([op, op])
    with pytest.raises(ValueError):
        gw.update("t", {"pk": "a"}, "SET #n = :v", names={"#n": "n"}, values={":v": 1, ":unused": 3})
