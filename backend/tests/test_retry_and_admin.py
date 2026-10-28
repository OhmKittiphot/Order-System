"""Admin recovery: retry eligibility, retry execution, cancel, DLQ, stats."""

from __future__ import annotations

from conftest import ADMIN, CUSTOMER, api, order, place_order, stock


def test_business_failure_not_retryable_until_restocked(env):
    oid = place_order([("prd_seed_mug", 3)]).data["orderId"]
    env.drain()
    detail = api("GET", f"/admin/orders/{oid}", user=ADMIN).data
    assert detail["retry"]["retryable"] is False
    assert detail["retry"]["category"] == "BUSINESS"
    res = api("POST", f"/admin/orders/{oid}/retry", user=ADMIN)
    assert res.status == 409 and res.error["code"] == "NOT_RETRYABLE"

    api("PATCH", "/admin/products/prd_seed_mug/stock", user=ADMIN, body={"mode": "adjust", "quantity": 5})
    detail = api("GET", f"/admin/orders/{oid}", user=ADMIN).data
    assert detail["retry"] == {
        "retryable": True,
        "action": "RESTART",
        "reason": "Stock is now available; the order can be processed again",
        "category": "BUSINESS",
    }
    res = api("POST", f"/admin/orders/{oid}/retry", user=ADMIN)
    assert res.status == 202 and res.data["attempt"] == 1 and res.data["status"] == "PENDING"
    env.drain()
    o = order(env, oid)
    assert o["status"] == "CONFIRMED" and "failureReason" not in o
    assert stock(env, "prd_seed_mug")["available"] == 3
    # two notifications: the failure (attempt 0) and the confirmation (attempt 1)
    types = sorted(n["type"] for n in api("GET", "/notifications", user=CUSTOMER).data["items"])
    assert types == ["OrderConfirmed", "OrderFailed"]


def test_payment_declined_is_not_retryable(env):
    oid = place_order([("prd_test_decline", 1)]).data["orderId"]
    env.drain()
    res = api("POST", f"/admin/orders/{oid}/retry", user=ADMIN)
    assert res.status == 409
    assert res.error["details"]["category"] == "PAYMENT_DECLINED"


def test_dlq_recovery_with_admin_retry(env, clock):
    oid = place_order([("prd_test_flaky", 2)]).data["orderId"]
    env.drain()
    assert env.bus.counts()["payment"]["dlq"] == 1
    # not yet considered stuck
    assert api("POST", f"/admin/orders/{oid}/retry", user=ADMIN).status == 409
    clock.advance(121)
    status = api("GET", "/admin/dlq-status", user=ADMIN).data
    payment_q = next(q for q in status["queues"] if q["name"] == "payment")
    assert payment_q["dlqVisible"] == 1
    assert status["stuckOrders"][0]["orderId"] == oid
    assert any(a["state"] == "ALARM" for a in status["alarms"])

    res = api("POST", f"/admin/orders/{oid}/retry", user=ADMIN)
    assert res.status == 202
    assert res.data["action"] == "REPUBLISH_INVENTORY_RESERVED" and res.data["eventPublished"] is True
    env.drain()
    o = order(env, oid)
    assert (o["status"], o["paymentStatus"], o["attempt"]) == ("CONFIRMED", "SUCCEEDED", 1)
    inv = stock(env, "prd_test_flaky")
    assert (inv["available"], inv["reserved"], inv["sold"]) == (98, 0, 2)
    # redriving the stale DLQ message afterwards is harmless
    assert api("POST", "/admin/dlq/payment/redrive", user=ADMIN).status == 202
    env.drain()
    assert len(env.deps.payments.list_for_order(oid)) == 1
    assert env.bus.counts()["payment"] == {"queue": 0, "dlq": 0}


def test_duplicate_retry_requests_are_rejected(env, clock):
    oid = place_order([("prd_seed_mug", 2)]).data["orderId"]
    env.drain()
    api("PATCH", "/admin/products/prd_seed_mug/stock", user=ADMIN, body={"mode": "set", "quantity": 0})
    env.deps.catalog.set_available("prd_seed_mug", 50)
    first = api("POST", f"/admin/orders/{oid}/retry", user=ADMIN)
    second = api("POST", f"/admin/orders/{oid}/retry", user=ADMIN)
    assert first.status == 202
    assert second.status == 409  # order is PENDING now, not retryable / cooldown


def test_retry_optimistic_lock_blocks_concurrent_admins(env, clock, monkeypatch):
    from order_system.repositories.orders import OrdersRepository
    from order_system.services.retry_service import RetryService

    oid = place_order([("prd_seed_mug", 2)]).data["orderId"]
    env.drain()
    env.deps.catalog.set_available("prd_seed_mug", 10)
    svc = RetryService(env.deps)
    snapshot = order(env, oid)
    monkeypatch.setattr(OrdersRepository, "get", lambda self, _id: dict(snapshot))  # both admins read the same version
    assert svc.retry(oid, "admin-a", "c1")["attempt"] == 1
    try:
        svc.retry(oid, "admin-b", "c2")
        raise AssertionError("second retry should conflict")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", "") == "RETRY_CONFLICT"


def test_cancel_processing_order_releases_stock(env):
    oid = place_order([("prd_test_flaky", 4)]).data["orderId"]
    env.drain()  # stuck in PROCESSING with stock reserved
    assert stock(env, "prd_test_flaky")["reserved"] == 4
    res = api("POST", f"/admin/orders/{oid}/cancel", user=ADMIN)
    assert res.status == 200 and res.data["stockReleased"] is True
    inv = stock(env, "prd_test_flaky")
    assert (inv["available"], inv["reserved"]) == (100, 0)
    assert order(env, oid)["status"] == "CANCELLED"
    assert api("POST", f"/admin/orders/{oid}/cancel", user=ADMIN).status == 409


def test_confirmed_order_cannot_be_cancelled_or_retried(env):
    oid = place_order([("prd_seed_hub", 1)]).data["orderId"]
    env.drain()
    assert api("POST", f"/admin/orders/{oid}/cancel", user=ADMIN).status == 409
    assert api("POST", f"/admin/orders/{oid}/retry", user=ADMIN).status == 409


def test_admin_stats_and_filters(env):
    place_order([("prd_seed_hub", 1)], key="stats-key-01")
    place_order([("prd_seed_mug", 9)], key="stats-key-02")
    env.drain()
    stats = api("GET", "/admin/stats", user=ADMIN).data
    assert stats["orders"]["total"] == 2
    assert stats["orders"]["byStatus"]["CONFIRMED"] == 1
    assert stats["orders"]["byStatus"]["FAILED"] == 1
    assert stats["products"]["total"] == 8
    assert stats["products"]["lowStock"] == 3  # monitor(5), stand(3), mug(1)
    failed = api("GET", "/admin/orders", user=ADMIN, query={"status": "FAILED"}).data["items"]
    assert len(failed) == 1 and failed[0]["retry"]["retryable"] is False
    assert api("GET", "/admin/orders", user=ADMIN, query={"status": "WHATEVER"}).status == 400
    everything = api("GET", "/admin/orders", user=ADMIN).data["items"]
    assert len(everything) == 2


def test_redrive_unknown_queue_rejected(env):
    assert api("POST", "/admin/dlq/orders/redrive", user=ADMIN).status == 400
