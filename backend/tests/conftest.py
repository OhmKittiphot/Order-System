"""Test fixtures. Tests run fully offline: the real application code runs
against the in-memory DynamoDB/SNS/SQS stand-ins in ``backend/local``."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))
sys.path.insert(0, str(BACKEND / "local"))

from order_system.services.container import set_deps  # noqa: E402
from order_system.utils import common  # noqa: E402
from order_system_local.environment import LocalEnv, build_local_env  # noqa: E402
from order_system_local.routes import match  # noqa: E402

CUSTOMER = ("cust-1111", "customer")
OTHER = ("cust-2222", "customer")
ADMIN = ("admin-9999", "admin")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 27, 8, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock():  # type: ignore[no-untyped-def]
    c = Clock()
    common.set_clock(c)
    yield c
    common.set_clock(None)


@pytest.fixture
def env(clock: Clock) -> Any:  # type: ignore[no-untyped-def]
    e = build_local_env()
    e.seed_products()
    yield e
    set_deps(None)


@pytest.fixture
def email_env(clock: Clock) -> Any:  # type: ignore[no-untyped-def]
    e = build_local_env(email=True)
    e.seed_products()
    yield e
    set_deps(None)


class ApiResult:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.status = raw["statusCode"]
        self.headers = raw["headers"]
        self.body = json.loads(raw["body"])

    @property
    def data(self) -> Any:
        return self.body.get("data")

    @property
    def error(self) -> Any:
        return self.body.get("error")


def api(
    method: str,
    path: str,
    *,
    user: tuple[str, str] | None = None,
    body: Any = None,
    headers: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
) -> ApiResult:
    """Invoke the real Lambda handler the way API Gateway would."""
    found = match(method, path)
    assert found, f"no route for {method} {path}"
    route_key, handler, needs_auth, params = found
    ctx: dict[str, Any] = {"requestId": "test-req-0001", "http": {"method": method, "path": path}}
    if user is not None:
        # What the Lambda Authorizer returns as context for a verified token.
        ctx["authorizer"] = {"lambda": {"userId": user[0], "role": user[1], "email": ""}}
    elif needs_auth:
        # API Gateway would reject this before the Lambda runs; handlers must also refuse.
        pass
    event = {
        "routeKey": route_key,
        "rawPath": path,
        "headers": headers or {},
        "queryStringParameters": query,
        "pathParameters": params or None,
        "body": json.dumps(body) if body is not None and not isinstance(body, str) else body,
        "requestContext": ctx,
    }
    return ApiResult(handler(event, None))


def place_order(items: list[tuple[str, int]], *, user=CUSTOMER, key: str = "key-00000001") -> ApiResult:  # type: ignore[no-untyped-def]
    return api(
        "POST",
        "/orders",
        user=user,
        headers={"idempotency-key": key},
        body={"items": [{"productId": p, "quantity": q} for p, q in items]},
    )


def stock(env: LocalEnv, product_id: str) -> dict[str, Any]:
    return env.deps.catalog.get_inventory(product_id) or {}


def order(env: LocalEnv, order_id: str) -> dict[str, Any]:
    return env.deps.orders.get(order_id) or {}
