"""Authorization boundaries: ownership, admin role, authentication."""

from __future__ import annotations

import pytest

from conftest import ADMIN, CUSTOMER, OTHER, api, place_order

ADMIN_ROUTES = [
    ("GET", "/admin/orders", None),
    ("GET", "/admin/orders/ord_x", None),
    ("POST", "/admin/orders/ord_x/retry", None),
    ("POST", "/admin/orders/ord_x/cancel", None),
    ("GET", "/admin/products", None),
    ("POST", "/admin/products", {"name": "x", "priceMinor": 1}),
    ("GET", "/admin/products/prd_seed_hub", None),
    ("PATCH", "/admin/products/prd_seed_hub", {"priceMinor": 1}),
    ("PATCH", "/admin/products/prd_seed_hub/stock", {"mode": "set", "quantity": 0}),
    ("GET", "/admin/stats", None),
    ("GET", "/admin/dlq-status", None),
    ("POST", "/admin/dlq/stock/redrive", None),
]


def test_customer_cannot_read_another_customers_order(env):
    oid = place_order([("prd_seed_hub", 1)], user=CUSTOMER).data["orderId"]
    res = api("GET", f"/orders/{oid}", user=OTHER)
    assert res.status == 404  # existence is not revealed
    assert api("GET", "/orders", user=OTHER).data["items"] == []
    assert api("GET", f"/orders/{oid}", user=CUSTOMER).status == 200


def test_admin_can_read_any_order_with_internal_fields(env):
    oid = place_order([("prd_test_decline", 1)], user=CUSTOMER).data["orderId"]
    res = api("GET", f"/orders/{oid}", user=ADMIN)
    assert res.status == 200
    assert res.data["items"][0]["testBehavior"] == "PAYMENT_DECLINE"
    customer_view = api("GET", f"/orders/{oid}", user=CUSTOMER).data
    assert "testBehavior" not in customer_view["items"][0]
    assert "version" not in customer_view


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_customers_cannot_invoke_admin_endpoints(env, method, path, body):
    res = api(method, path, user=CUSTOMER, body=body)
    assert res.status == 403
    assert res.error["code"] == "FORBIDDEN"


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_unauthenticated_admin_calls_are_rejected(env, method, path, body):
    assert api(method, path, body=body).status == 401


def test_unauthenticated_customer_calls_are_rejected(env):
    assert api("GET", "/orders").status == 401
    assert api("GET", "/notifications").status == 401
    assert api("POST", "/orders", body={"items": []}, headers={"idempotency-key": "abcdefgh1"}).status == 401


def test_role_in_request_body_is_ignored(env):
    res = api(
        "POST",
        "/admin/products",
        user=CUSTOMER,
        body={"name": "Hack", "priceMinor": 1, "role": "admin", "isAdmin": True},
    )
    assert res.status == 403


def test_errors_do_not_leak_internals(env, monkeypatch):
    from order_system.services import order_service

    def boom(*_a, **_k):
        raise RuntimeError("secret connection string xyz")

    monkeypatch.setattr(order_service.OrderService, "list_my_orders", boom)
    res = api("GET", "/orders", user=CUSTOMER)
    assert res.status == 500
    assert "secret" not in str(res.body)
    assert res.error["code"] == "INTERNAL_ERROR"


def test_unknown_route_and_bad_ids(env):
    assert api("GET", "/orders/bad id!", user=CUSTOMER).status == 400
    assert api("GET", "/products/x").status == 400  # too short to be an id


def test_admin_product_management_validates_input(env):
    assert api("POST", "/admin/products", user=ADMIN, body={"name": "", "priceMinor": 100}).status == 400
    assert api("POST", "/admin/products", user=ADMIN, body={"name": "X", "priceMinor": -5}).status == 400
    assert (
        api(
            "POST",
            "/admin/products",
            user=ADMIN,
            body={"name": "X", "priceMinor": 5, "imageUrl": "javascript:alert(1)"},
        ).status
        == 400
    )
    assert (
        api("PATCH", "/admin/products/prd_seed_hub/stock", user=ADMIN, body={"mode": "set", "quantity": -1}).status
        == 400
    )
    res = api("PATCH", "/admin/products/prd_seed_hub/stock", user=ADMIN, body={"mode": "adjust", "quantity": -41})
    assert res.status == 409 and res.error["code"] == "NEGATIVE_STOCK"
    res = api("PATCH", "/admin/products/prd_seed_hub/stock", user=ADMIN, body={"mode": "adjust", "quantity": -40})
    assert res.status == 200 and res.data["available"] == 0
    assert (
        api("PATCH", "/admin/products/prd_nope_123/stock", user=ADMIN, body={"mode": "set", "quantity": 1}).status
        == 404
    )


def test_admin_creates_and_edits_product(env):
    res = api(
        "POST",
        "/admin/products",
        user=ADMIN,
        body={"name": "Webcam", "description": "1080p", "priceMinor": 159000, "initialStock": 7},
    )
    assert res.status == 201
    pid = res.data["productId"]
    assert res.data["available"] == 7 and res.data["active"] is True
    res = api("PATCH", f"/admin/products/{pid}", user=ADMIN, body={"priceMinor": 149000, "active": False})
    assert res.data["priceMinor"] == 149000 and res.data["active"] is False
    assert api("GET", f"/products/{pid}").status == 404  # inactive is hidden from customers
    names = [p["name"] for p in api("GET", "/admin/products", user=ADMIN).data["items"]]
    assert "Webcam" in names
