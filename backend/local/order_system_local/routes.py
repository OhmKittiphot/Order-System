"""Route table mirrored from terraform/api_gateway.tf.

``tests/test_consistency.py`` asserts that every route here exists in the
Terraform configuration with the same authorization type, so the local dev
server and the deployed API cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from order_system.handlers import api_admin, api_auth, api_orders, api_products

Handler = Callable[[dict[str, Any], Any], dict[str, Any]]

# (route key, lambda handler, requires JWT)
ROUTES: list[tuple[str, Handler, bool]] = [
    ("POST /auth/register", api_auth.handler, False),
    ("POST /auth/login", api_auth.handler, False),
    ("POST /auth/refresh", api_auth.handler, False),
    ("GET /me", api_auth.handler, True),
    ("GET /products", api_products.handler, False),
    ("GET /products/{productId}", api_products.handler, False),
    ("POST /orders", api_orders.handler, True),
    ("GET /orders", api_orders.handler, True),
    ("GET /orders/{orderId}", api_orders.handler, True),
    ("GET /notifications", api_orders.handler, True),
    ("GET /admin/orders", api_admin.handler, True),
    ("GET /admin/orders/{orderId}", api_admin.handler, True),
    ("POST /admin/orders/{orderId}/retry", api_admin.handler, True),
    ("POST /admin/orders/{orderId}/cancel", api_admin.handler, True),
    ("GET /admin/products", api_admin.handler, True),
    ("POST /admin/products", api_admin.handler, True),
    ("GET /admin/products/{productId}", api_admin.handler, True),
    ("PATCH /admin/products/{productId}", api_admin.handler, True),
    ("PATCH /admin/products/{productId}/stock", api_admin.handler, True),
    ("GET /admin/stats", api_admin.handler, True),
    ("GET /admin/dlq-status", api_admin.handler, True),
    ("POST /admin/dlq/{queue}/redrive", api_admin.handler, True),
]


def match(method: str, path: str) -> tuple[str, Handler, bool, dict[str, str]] | None:
    parts = [p for p in path.split("/") if p]
    for route_key, handler, auth in ROUTES:
        route_method, template = route_key.split(" ", 1)
        if route_method != method:
            continue
        tparts = [p for p in template.split("/") if p]
        if len(tparts) != len(parts):
            continue
        params: dict[str, str] = {}
        for t, p in zip(tparts, parts, strict=True):
            if t.startswith("{") and t.endswith("}"):
                params[t[1:-1]] = p
            elif t != p:
                break
        else:
            return route_key, handler, auth, params
    return None
