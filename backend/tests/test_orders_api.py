"""Order creation: validation, server-side pricing, idempotency, reliable publish."""

from __future__ import annotations

from conftest import CUSTOMER, OTHER, api, order, place_order


def test_create_order_returns_202_pending_with_server_side_total(env):
    res = place_order([("prd_seed_earbuds", 2), ("prd_seed_hub", 1)])
    assert res.status == 202
    data = res.data
    assert data["status"] == "PENDING"
    assert data["inventoryStatus"] == "PENDING"
    assert data["paymentStatus"] == "PENDING"
    assert data["totalMinor"] == 2 * 129000 + 89000
    assert data["items"][0]["unitPriceMinor"] == 129000
    assert res.headers["X-Correlation-Id"] == "test-req-0001"
    stored = order(env, data["orderId"])
    assert stored["customerId"] == CUSTOMER[0]
    assert stored["totalMinor"] == data["totalMinor"]
    # event published and outbox marker cleared
    assert [e.eventType for e in env.bus.published] == ["OrderPlaced"]
    assert "outboxStatus" not in stored


def test_client_supplied_price_or_total_is_rejected(env):
    res = api(
        "POST",
        "/orders",
        user=CUSTOMER,
        headers={"idempotency-key": "key-00000002"},
        body={"items": [{"productId": "prd_seed_earbuds", "quantity": 1, "priceMinor": 1}], "totalMinor": 1},
    )
    assert res.status == 400
    assert res.error["code"] == "VALIDATION_ERROR"


def test_duplicate_lines_are_merged(env):
    res = place_order([("prd_seed_hub", 1), ("prd_seed_hub", 2)])
    assert res.status == 202
    assert res.data["items"] == [
        {
            "productId": "prd_seed_hub",
            "name": "USB-C Hub 7-in-1",
            "unitPriceMinor": 89000,
            "quantity": 3,
            "lineTotalMinor": 267000,
        }
    ]


def test_invalid_product_ids_and_inactive_products(env):
    res = place_order([("prd_does_not_exist", 1)])
    assert res.status == 400
    assert res.error["code"] == "INVALID_PRODUCTS"
    api("PATCH", "/admin/products/prd_seed_hub", user=("admin", "admin"), body={"active": False})
    res = place_order([("prd_seed_hub", 1)], key="key-00000003")
    assert res.status == 400
    assert res.error["details"]["productIds"] == ["prd_seed_hub"]


def test_invalid_quantities(env):
    for qty in (0, -1, 100, 1.5, "2", True):
        res = api(
            "POST",
            "/orders",
            user=CUSTOMER,
            headers={"idempotency-key": "key-00000004"},
            body={"items": [{"productId": "prd_seed_hub", "quantity": qty}]},
        )
        assert res.status == 400, qty
    res = api("POST", "/orders", user=CUSTOMER, headers={"idempotency-key": "key-00000004"}, body={"items": []})
    assert res.status == 400
    res = api("POST", "/orders", user=CUSTOMER, headers={"idempotency-key": "key-00000004"}, body="not json")
    assert res.status == 400


def test_idempotency_key_required(env):
    res = api("POST", "/orders", user=CUSTOMER, body={"items": [{"productId": "prd_seed_hub", "quantity": 1}]})
    assert res.status == 400
    assert res.error["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_idempotent_order_creation(env):
    first = place_order([("prd_seed_hub", 1)], key="same-key-123")
    second = place_order([("prd_seed_hub", 1)], key="same-key-123")
    assert first.status == 202
    assert second.status == 200
    assert second.data["idempotentReplay"] is True
    assert second.data["orderId"] == first.data["orderId"]
    listed = api("GET", "/orders", user=CUSTOMER).data["items"]
    assert len(listed) == 1
    assert len(env.bus.published) == 1


def test_idempotency_key_reuse_with_different_body_conflicts(env):
    place_order([("prd_seed_hub", 1)], key="same-key-456")
    res = place_order([("prd_seed_hub", 2)], key="same-key-456")
    assert res.status == 409
    assert res.error["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_idempotency_keys_are_scoped_per_customer(env):
    a = place_order([("prd_seed_hub", 1)], key="shared-key-1", user=CUSTOMER)
    b = place_order([("prd_seed_hub", 1)], key="shared-key-1", user=OTHER)
    assert a.data["orderId"] != b.data["orderId"]


def test_publish_failure_leaves_outbox_marker_and_sweeper_recovers(env, clock):
    env.bus.fail_next_publishes = 3  # all in-request attempts fail
    res = place_order([("prd_seed_hub", 1)])
    assert res.status == 202  # order is safely stored
    stored = order(env, res.data["orderId"])
    assert stored["outboxStatus"] == "PENDING_PUBLISH"
    assert env.bus.published == []
    assert env.sweep_outbox()["found"] == 0  # too young: request may still be publishing
    clock.advance(31)
    assert env.sweep_outbox() == {"found": 1, "published": 1, "failed": 0}
    assert "outboxStatus" not in order(env, res.data["orderId"])
    env.drain()
    assert order(env, res.data["orderId"])["status"] == "CONFIRMED"


def test_order_history_pagination(env):
    ids = []
    for i in range(5):
        ids.append(place_order([("prd_seed_hub", 1)], key=f"page-key-{i:04d}").data["orderId"])
    page1 = api("GET", "/orders", user=CUSTOMER, query={"limit": "2"}).data
    assert len(page1["items"]) == 2 and page1["nextToken"]
    page2 = api("GET", "/orders", user=CUSTOMER, query={"limit": "2", "nextToken": page1["nextToken"]}).data
    page3 = api("GET", "/orders", user=CUSTOMER, query={"limit": "2", "nextToken": page2["nextToken"]}).data
    seen = [o["orderId"] for o in page1["items"] + page2["items"] + page3["items"]]
    assert sorted(seen) == sorted(ids)
    assert page3["nextToken"] is None


def test_bad_pagination_inputs(env):
    assert api("GET", "/orders", user=CUSTOMER, query={"limit": "0"}).status == 400
    assert api("GET", "/orders", user=CUSTOMER, query={"nextToken": "%%%"}).status == 400


def test_public_product_listing_hides_test_hooks(env):
    res = api("GET", "/products")
    assert res.status == 200
    items = res.data["items"]
    assert len(items) == 8
    assert all("testBehavior" not in p for p in items)
    mug = next(p for p in items if p["productId"] == "prd_seed_mug")
    assert mug["available"] == 1 and mug["inStock"] is True
    assert api("GET", "/products/prd_seed_mug").data["name"] == "Limited Edition Mug"
    assert api("GET", "/products/prd_nope").status == 404
