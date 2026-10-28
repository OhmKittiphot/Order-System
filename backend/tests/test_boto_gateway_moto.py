"""Runs the full order workflow against the REAL boto3 DynamoDB gateway using
moto's mocked DynamoDB. This validates the boto3 serialisation layer that
the in-memory tests cannot cover.

Skipped automatically when boto3/moto are not installed:

    pip install -r requirements-dev.txt
    pytest tests/test_boto_gateway_moto.py -v
"""

from __future__ import annotations

import os

import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

from order_system.repositories.gateway import BotoDynamoGateway  # noqa: E402
from order_system.repositories.tables import LAYOUTS, physical_name  # noqa: E402
from order_system.services.container import Deps, set_deps  # noqa: E402
from order_system_local.environment import SEED_FILE, LocalEnv, local_settings  # noqa: E402
from order_system_local.fakes import FakeQueueAdmin, InMemoryBus  # noqa: E402


@pytest.fixture
def boto_env(clock):  # type: ignore[no-untyped-def]
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    with moto.mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        settings = local_settings()
        for logical, layout in LAYOUTS.items():
            attrs = {layout.partition_key: "S"}
            keys = [{"AttributeName": layout.partition_key, "KeyType": "HASH"}]
            if layout.sort_key:
                attrs[layout.sort_key] = "N" if layout.sort_key == "attempt" else "S"
                keys.append({"AttributeName": layout.sort_key, "KeyType": "RANGE"})
            gsis = []
            for name, (pk, sk) in layout.indexes.items():
                attrs[pk] = "S"
                schema = [{"AttributeName": pk, "KeyType": "HASH"}]
                if sk:
                    attrs[sk] = "S"
                    schema.append({"AttributeName": sk, "KeyType": "RANGE"})
                gsis.append({"IndexName": name, "KeySchema": schema, "Projection": {"ProjectionType": "ALL"}})
            kwargs = {
                "TableName": physical_name(settings, logical),
                "AttributeDefinitions": [{"AttributeName": k, "AttributeType": t} for k, t in attrs.items()],
                "KeySchema": keys,
                "BillingMode": "PAY_PER_REQUEST",
            }
            if gsis:
                kwargs["GlobalSecondaryIndexes"] = gsis
            client.create_table(**kwargs)
        bus = InMemoryBus()
        deps = Deps(
            settings=settings,
            gw=BotoDynamoGateway(client),
            publisher=bus,
            email=None,
            queues=FakeQueueAdmin(bus),
            alarms=None,
        )
        set_deps(deps)
        env = LocalEnv(deps=deps, gw=deps.gw, bus=bus, email=None)  # type: ignore[arg-type]
        env.seed_products(SEED_FILE)
        yield env
        set_deps(None)


def test_full_workflow_with_boto_gateway(boto_env):
    from conftest import CUSTOMER, api, place_order

    env = boto_env
    ok_id = place_order([("prd_seed_earbuds", 2)], key="moto-key-001").data["orderId"]
    oos_id = place_order([("prd_seed_mug", 3)], key="moto-key-002").data["orderId"]
    dec_id = place_order([("prd_test_decline", 1)], key="moto-key-003").data["orderId"]
    env.drain()
    assert env.deps.orders.get(ok_id)["status"] == "CONFIRMED"
    assert env.deps.orders.get(oos_id)["inventoryStatus"] == "OUT_OF_STOCK"
    assert env.deps.orders.get(dec_id)["inventoryStatus"] == "RELEASED"
    inv = env.deps.catalog.get_inventory("prd_seed_earbuds")
    assert (inv["available"], inv["reserved"], inv["sold"]) == (23, 0, 2)
    history = api("GET", "/orders", user=CUSTOMER).data["items"]
    assert len(history) == 3
    assert len(api("GET", "/notifications", user=CUSTOMER).data["items"]) == 3
    assert api("GET", "/products").data["items"]
