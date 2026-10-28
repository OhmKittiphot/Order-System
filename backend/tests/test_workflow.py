"""Asynchronous processing: stock, payment, notification, duplicates, races, DLQ."""

from __future__ import annotations

import json

from conftest import CUSTOMER, OTHER, api, order, place_order, stock
from order_system.models.events import EventType, OrderEvent
from order_system.services.workflow_service import WorkflowService


def test_successful_order_end_to_end(env):
    oid = place_order([("prd_seed_earbuds", 2)]).data["orderId"]
    env.drain()
    o = order(env, oid)
    assert (o["status"], o["inventoryStatus"], o["paymentStatus"], o["notificationStatus"]) == (
        "CONFIRMED",
        "COMMITTED",
        "SUCCEEDED",
        "SENT",
    )
    inv = stock(env, "prd_seed_earbuds")
    assert (inv["available"], inv["reserved"], inv["sold"]) == (23, 0, 2)
    assert [e.eventType for e in env.bus.published] == ["OrderPlaced", "InventoryReserved", "OrderConfirmed"]
    payments = env.deps.payments.list_for_order(oid)
    assert len(payments) == 1 and payments[0]["status"] == "SUCCEEDED" and payments[0]["amountMinor"] == 258000
    notes = api("GET", "/notifications", user=CUSTOMER).data["items"]
    assert len(notes) == 1 and notes[0]["type"] == "OrderConfirmed" and notes[0]["emailStatus"] == "NOT_CONFIGURED"
    timeline = [h["event"] for h in o["history"]]
    assert timeline == ["OrderCreated", "InventoryReserved", "PaymentSucceeded", "CustomerNotified"]
    assert o["updatedAt"] >= o["createdAt"]


def test_out_of_stock_order_fails_without_touching_stock(env):
    oid = place_order([("prd_seed_mug", 2), ("prd_seed_hub", 1)]).data["orderId"]
    env.drain()
    o = order(env, oid)
    assert (o["status"], o["inventoryStatus"], o["paymentStatus"]) == ("FAILED", "OUT_OF_STOCK", "SKIPPED")
    assert o["failureCategory"] == "BUSINESS"
    assert "Limited Edition Mug" in o["failureReason"]
    # all-or-nothing: the hub line was not reserved either
    assert stock(env, "prd_seed_hub")["available"] == 40
    assert stock(env, "prd_seed_mug")["available"] == 1
    assert env.deps.payments.list_for_order(oid) == []
    assert o["notificationStatus"] == "SENT"


def test_payment_failure_releases_reserved_stock(env):
    oid = place_order([("prd_test_decline", 3), ("prd_seed_hub", 2)]).data["orderId"]
    env.drain()
    o = order(env, oid)
    assert (o["status"], o["inventoryStatus"], o["paymentStatus"]) == ("FAILED", "RELEASED", "FAILED")
    assert o["failureCategory"] == "PAYMENT_DECLINED"
    for pid, start in (("prd_test_decline", 100), ("prd_seed_hub", 40)):
        inv = stock(env, pid)
        assert (inv["available"], inv["reserved"], inv["sold"]) == (start, 0, 0)
    assert env.deps.payments.list_for_order(oid)[0]["status"] == "FAILED"
    assert api("GET", "/notifications", user=CUSTOMER).data["items"][0]["type"] == "OrderFailed"


def test_concurrent_orders_for_last_unit(env):
    """Two customers race for the single mug: exactly one wins, stock never negative."""
    a = place_order([("prd_seed_mug", 1)], user=CUSTOMER, key="race-key-a1").data["orderId"]
    b = place_order([("prd_seed_mug", 1)], user=OTHER, key="race-key-b1").data["orderId"]
    env.drain()
    statuses = sorted([order(env, a)["status"], order(env, b)["status"]])
    assert statuses == ["CONFIRMED", "FAILED"]
    inv = stock(env, "prd_seed_mug")
    assert (inv["available"], inv["reserved"], inv["sold"]) == (0, 0, 1)


def test_inventory_reservation_is_atomic_under_interleaving(env):
    """Simulates two stock workers handling different orders at once: both
    read 'PENDING', but the conditional transaction lets only one reserve."""
    a = place_order([("prd_seed_stand", 3)], key="atomic-key-a").data["orderId"]
    b = place_order([("prd_seed_stand", 2)], key="atomic-key-b", user=OTHER).data["orderId"]
    wf = WorkflowService(env.deps)
    ev_a = OrderEvent.create(EventType.ORDER_PLACED, order(env, a))
    ev_b = OrderEvent.create(EventType.ORDER_PLACED, order(env, b))
    assert wf.handle_order_placed(ev_a) == "RESERVED"
    assert wf.handle_order_placed(ev_b) == "OUT_OF_STOCK"
    assert stock(env, "prd_seed_stand")["available"] == 0
    assert stock(env, "prd_seed_stand")["reserved"] == 3


def test_duplicate_order_placed_does_not_decrement_twice(env):
    oid = place_order([("prd_seed_keyboard", 2)]).data["orderId"]
    message = env.bus.queues["stock"][0]
    env.bus.queues["stock"].append(type(message)("dup-1", message.body))  # SQS duplicate delivery
    env.drain()
    inv = stock(env, "prd_seed_keyboard")
    assert (inv["available"], inv["reserved"], inv["sold"]) == (10, 0, 2)
    assert len(env.deps.payments.list_for_order(oid)) == 1
    assert order(env, oid)["status"] == "CONFIRMED"


def test_duplicate_inventory_reserved_creates_one_payment(env):
    oid = place_order([("prd_seed_keyboard", 1)]).data["orderId"]
    env.bus.drain({"stock": env.handlers["stock"]})  # only run stock step
    pay_msg = env.bus.queues["payment"][0]
    env.bus.queues["payment"].append(type(pay_msg)("dup-2", pay_msg.body))
    env.drain()
    assert len(env.deps.payments.list_for_order(oid)) == 1
    assert stock(env, "prd_seed_keyboard")["sold"] == 1
    notes = api("GET", "/notifications", user=CUSTOMER).data["items"]
    assert len(notes) == 1  # dedupe even though OrderConfirmed may be re-published


def test_notification_deduplication(env):
    oid = place_order([("prd_seed_hub", 1)]).data["orderId"]
    env.drain()
    ev = OrderEvent.create(EventType.ORDER_CONFIRMED, order(env, oid))
    wf = WorkflowService(env.deps)
    assert wf.handle_order_outcome(ev) == "DUPLICATE"
    assert wf.handle_order_outcome(ev) == "DUPLICATE"
    assert len(api("GET", "/notifications", user=CUSTOMER).data["items"]) == 1


def test_email_notification_recorded_as_accepted_not_delivered(email_env):
    env = email_env
    place_order([("prd_seed_hub", 1)])
    env.drain()
    note = api("GET", "/notifications", user=CUSTOMER).data["items"][0]
    assert note["emailStatus"] == "ACCEPTED_BY_SNS"
    assert note["channels"] == ["IN_APP", "EMAIL"]
    assert len(env.email.sent) == 1 and env.email.sent[0]["customerId"] == CUSTOMER[0]


def test_email_outage_retries_without_duplicate_records(email_env):
    env = email_env
    oid = place_order([("prd_seed_hub", 1)]).data["orderId"]
    env.email.fail_next = 1
    env.drain()
    assert len(env.email.sent) == 1  # retried by SQS redelivery
    assert len(api("GET", "/notifications", user=CUSTOMER).data["items"]) == 1
    assert order(env, oid)["notificationStatus"] == "SENT"


def test_late_event_cannot_overwrite_terminal_state(env):
    oid = place_order([("prd_seed_hub", 1)]).data["orderId"]
    first_event = env.bus.queues["stock"][0].body
    env.drain()
    assert order(env, oid)["status"] == "CONFIRMED"
    # The original OrderPlaced arrives again much later.
    result = WorkflowService(env.deps).handle_order_placed(OrderEvent.parse(first_event))
    assert result == "DUPLICATE"
    assert order(env, oid)["status"] == "CONFIRMED"
    assert stock(env, "prd_seed_hub")["available"] == 39


def test_stale_attempt_event_is_ignored(env, clock):
    oid = place_order([("prd_seed_mug", 5)]).data["orderId"]
    old_event = env.bus.queues["stock"][0].body
    env.drain()
    assert order(env, oid)["status"] == "FAILED"
    api("PATCH", "/admin/products/prd_seed_mug/stock", user=("a", "admin"), body={"mode": "set", "quantity": 10})
    assert api("POST", f"/admin/orders/{oid}/retry", user=("a", "admin")).status == 202
    # an old attempt-0 event delivered now must not touch attempt 1
    assert WorkflowService(env.deps).handle_order_placed(OrderEvent.parse(old_event)) == "STALE"
    env.drain()
    o = order(env, oid)
    assert o["status"] == "CONFIRMED" and o["attempt"] == 1
    assert stock(env, "prd_seed_mug")["sold"] == 5


def test_transient_payment_failure_goes_to_dlq_after_three_receives(env):
    oid = place_order([("prd_test_flaky", 1)]).data["orderId"]
    env.drain()
    counts = env.bus.counts()
    assert counts["payment"] == {"queue": 0, "dlq": 1}
    o = order(env, oid)
    assert (o["status"], o["inventoryStatus"], o["paymentStatus"]) == ("PROCESSING", "RESERVED", "PENDING")
    assert o["processingAttempts"] == 4  # 1 stock + 3 payment receives
    assert env.bus.dlqs["payment"][0].receive_count == 3


def test_permanent_invalid_messages_are_parked_not_retried(env):
    handler = env.handlers["stock"]
    result = handler(
        {
            "Records": [
                {"messageId": "bad-json", "body": "{not json", "attributes": {"ApproximateReceiveCount": "1"}},
                {
                    "messageId": "unknown-order",
                    "attributes": {"ApproximateReceiveCount": "1"},
                    "body": json.dumps(
                        {
                            "eventId": "e1",
                            "eventType": "OrderPlaced",
                            "orderId": "ord_missing",
                            "customerId": "c",
                            "attempt": 0,
                            "schemaVersion": "1.0",
                        }
                    ),
                },
                {
                    "messageId": "wrong-type",
                    "attributes": {"ApproximateReceiveCount": "1"},
                    "body": json.dumps(
                        {
                            "eventId": "e2",
                            "eventType": "OrderConfirmed",
                            "orderId": "x",
                            "customerId": "c",
                            "attempt": 0,
                        }
                    ),
                },
            ]
        }
    )
    assert result == {"batchItemFailures": []}  # not retried
    parked = env.bus.dlqs["stock"]
    assert len(parked) == 3
    assert all(m.attributes["failedService"] == "stock-worker" for m in parked)


def test_partial_batch_failure_only_fails_bad_records(env):
    good = place_order([("prd_seed_hub", 1)]).data["orderId"]
    flaky = place_order([("prd_test_flaky", 1)], key="key-flaky-01").data["orderId"]
    env.bus.drain({"stock": env.handlers["stock"]})
    records = [
        {"messageId": m.message_id, "body": m.body, "attributes": {"ApproximateReceiveCount": "1"}}
        for m in env.bus.queues["payment"]
    ]
    result = env.handlers["payment"]({"Records": records})
    failed = {f["itemIdentifier"] for f in result["batchItemFailures"]}
    assert len(records) == 2 and len(failed) == 1
    assert order(env, good)["status"] == "CONFIRMED"
    assert order(env, flaky)["status"] == "PROCESSING"


def test_publish_failure_after_commit_is_recovered_by_redelivery(env):
    """Stock commits, then SNS fails: SQS redelivers OrderPlaced and the
    worker re-publishes InventoryReserved instead of reserving again."""
    oid = place_order([("prd_seed_monitor", 1)]).data["orderId"]
    env.bus.fail_next_publishes = 3
    env.drain()
    o = order(env, oid)
    assert o["status"] == "CONFIRMED"
    assert stock(env, "prd_seed_monitor")["available"] == 4


def test_sns_envelope_messages_are_also_accepted():
    body = json.dumps(
        {
            "Type": "Notification",
            "Message": json.dumps(
                {"eventId": "e", "eventType": "OrderPlaced", "orderId": "o", "customerId": "c", "attempt": 0}
            ),
        }
    )
    assert OrderEvent.parse(body).orderId == "o"
